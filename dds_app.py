import os
import threading
import logging
import time
from typing import Callable, List, Optional, Iterable
import rti.connextdds as dds
from chat import ChatUser, ChatMessage  # generated automatically from chat.idl

# Callbacks for GUI
class Handlers:
    users_joined: Callable[[List[ChatUser]], None] = lambda *_: logging.warning("Not implemented")
    users_dropped: Callable[[List[ChatUser]], None] = lambda *_: logging.warning("Not implemented")
    message_received: Callable[[List[ChatMessage]], None] = lambda *_: logging.warning("Not implemented")

# DDS backend for the chat app: handles messaging, presence, and persistence.
class DDSApp:
    TOPIC_NAME_USER = "userInfo"
    TOPIC_NAME_MSG = "message"

    QOS_PROVIDER_XML = os.path.join(os.path.dirname(__file__), "chat_qos.xml")
    QOS_LIBRARY = "Chat_Library"
    QOS_PROFILE_USER = "ChatUser_Profile"
    QOS_PROFILE_MSG = "ChatMessage_Persistent_Profile"

    # Initialize DDS entities
    def __init__(self, user: ChatUser, handlers: Handlers = Handlers(),
                 auto_join: bool = True, domain_id: int = 0):
        self.user = user
        self.handlers = handlers

        # Load QoS from XML file
        self.qos_provider = dds.QosProvider(self.QOS_PROVIDER_XML)
        try:
            # Try to create participant with custom QoS
            part_qos = self.qos_provider.participant_qos_from_profile(
                f"{self.QOS_LIBRARY}::Chat_Profile"
            )
            self.participant = dds.DomainParticipant(domain_id, part_qos)
        except Exception:
            # fallback: default QoS
            self.participant = dds.DomainParticipant(domain_id)

        self.stop_condition = dds.GuardCondition()

        # ===== USER (presence) =====
        self.topic_user = dds.Topic(self.participant, self.TOPIC_NAME_USER, ChatUser)
        qos_user = self.qos_provider.datawriter_qos_from_profile(f"{self.QOS_LIBRARY}::{self.QOS_PROFILE_USER}")
        qos_user_r = self.qos_provider.datareader_qos_from_profile(f"{self.QOS_LIBRARY}::{self.QOS_PROFILE_USER}")
        self.writer_user = dds.DataWriter(self.topic_user, qos=qos_user)
        self.reader_user = dds.DataReader(self.topic_user, qos=qos_user_r)

        # Detect new or dropped users
        self.readcond_user = dds.ReadCondition(
            self.reader_user,
            dds.DataState(dds.SampleState.NOT_READ, dds.ViewState.ANY, dds.InstanceState.ANY)
        )
        self.waitset_user = dds.WaitSet()
        self.waitset_user.attach_condition(self.stop_condition)
        self.waitset_user.attach_condition(self.readcond_user)
        self.thread_user = threading.Thread(target=self._user_monitor, daemon=True)
        self.thread_user.start()

        # ===== MESSAGE (persistent) =====
        self.topic_msg = dds.Topic(self.participant, self.TOPIC_NAME_MSG, ChatMessage)
        self.pub_msg = dds.Publisher(self.participant)
        self.sub_msg = dds.Subscriber(self.participant)
        self._set_partition(self.pub_msg, self.user.group)
        self._set_partition(self.sub_msg, self.user.group)

        qos_profile_msg_str = f"{self.QOS_LIBRARY}::{self.QOS_PROFILE_MSG}"
        qos_writer = self.qos_provider.datawriter_qos_from_profile(qos_profile_msg_str)
        self.writer_msg = dds.DataWriter(self.pub_msg, self.topic_msg, qos=qos_writer)

        # Only receive messages for this user or their group (Custom)
        filter_expression = "toUser = %0 OR toGroup = %1"
        filter_parameters = [f"'{self.user.username}'", f"'{self.user.group}'"]
        self.reader_cft = dds.ContentFilteredTopic(
            self.topic_msg,
            "FilterByUsernameOrGroup",
            dds.Filter(filter_expression, filter_parameters)
        )

        reader_qos = self.qos_provider.datareader_qos_from_profile(qos_profile_msg_str)
        self.reader_msg = dds.DataReader(self.sub_msg, self.reader_cft, qos=reader_qos)

        # Monitor incoming chat messages
        self.readcond_msg = dds.ReadCondition(
            self.reader_msg,
            dds.DataState(dds.SampleState.NOT_READ, dds.ViewState.ANY, dds.InstanceState.ALIVE)
        )
        self.waitset_msg = dds.WaitSet()
        self.waitset_msg.attach_condition(self.stop_condition)
        self.waitset_msg.attach_condition(self.readcond_msg)
        self.thread_msg = threading.Thread(target=self._message_monitor, daemon=True)
        self.thread_msg.start()

        # Initialize message template
        self.message = ChatMessage()
        self.message.fromUser = self.user.username

        if auto_join:
            self.user_join()  # announce user presence

    # ===== User operations =====
    def user_join(self):
        self.writer_user.write(self.user)

    def user_update_group(self, group: str):
        self.user.group = group
        self._set_partition(self.pub_msg, self.user.group)
        self._set_partition(self.sub_msg, self.user.group)
        self.reader_cft.filter_parameters = [f"'{self.user.username}'", f"'{self.user.group}'"]
        self.writer_user.write(self.user)
    
    # Return currently active user
    def user_list(self) -> Iterable[ChatUser]:
        return self.reader_user.read_data()
    
    # ===== Messaging operations =====
    def message_send(self, destination: str, message: str):
        # Send a chat message (private or group)
        is_group = (destination == self.user.group)
        sample = ChatMessage()             
        sample.fromUser = self.user.username
        sample.toUser  = "" if is_group else destination
        sample.toGroup = destination if is_group else ""
        sample.message = message
        sample.timestamp_ms = int(time.time() * 1000)
        self.writer_msg.write(sample)

    # Retrieve all past messages (persistent)
    def message_history_all(self, limit: Optional[int] = None) -> List[ChatMessage]:
        sel = self.reader_msg.select().state(dds.DataState(
            dds.SampleState.ANY, dds.ViewState.ANY, dds.InstanceState.ANY
        )).read()
        samples = [s.data for s in sel if s.info.valid]
        if limit is not None and len(samples) > limit:
            samples = samples[-limit:]
        return samples
    
    # Search stored messages for a keyword
    def message_history_search(self, keyword: str, limit: Optional[int] = None) -> List[ChatMessage]:
        query_text = "(message LIKE %0) OR (fromUser LIKE %0) OR (toUser LIKE %0) OR (toGroup LIKE %0)"
        param = [f"'%{keyword}%'"]

        try:
            query = dds.Query(self.reader_msg, query_text, param)
            sel = (self.reader_msg
                .select()
                .state(dds.DataState(dds.SampleState.ANY, dds.ViewState.ANY, dds.InstanceState.ANY))
                .content(query)
                .read())
            results = [s.data for s in sel if s.info.valid]
        except Exception as e:
            results = []

        if not results:
            all_sel = (self.reader_msg
                    .select()
                    .state(dds.DataState(dds.SampleState.ANY, dds.ViewState.ANY, dds.InstanceState.ANY))
                    .read())
            all_msgs = [s.data for s in all_sel if s.info.valid]
            k = keyword.lower()
            def hit(m: ChatMessage) -> bool:
                return any(
                    (getattr(m, f) or "").lower().find(k) >= 0
                    for f in ("message", "fromUser", "toUser", "toGroup")
                )
            results = [m for m in all_msgs if hit(m)]

        if limit is not None and len(results) > limit:
            results = results[-limit:]
        return results
    
    # ===== Shutdown =====

    # Cleanly unregister user and stop threads
    def user_leave(self):  
        if self.participant.closed:
            return

        handle = self.writer_user.lookup_instance(self.user)
        if handle:
            self.writer_user.unregister_instance(handle)

        self.stop_condition.trigger_value = True
        self.thread_user.join()
        self.thread_msg.join()

        self.waitset_user.detach_all()
        self.waitset_msg.detach_all()
        self.participant.close_contained_entities()
        self.participant.close()

    # Apply DDS partition change
    def _set_partition(self, pubsub, partition_name: str):
        qos = pubsub.qos
        qos.partition.name = [partition_name]
        pubsub.qos = qos

    # Monitors user join and drop using WaitSet
    def _user_monitor(self):
        while True:
            active = self.waitset_user.wait(dds.Duration(1))
            for cond in active:
                if cond == self.stop_condition:
                    return
                if cond == self.readcond_user:
                    state_new = dds.DataState(dds.SampleState.NOT_READ, dds.ViewState.ANY, dds.InstanceState.ALIVE)
                    new_samples = self.reader_user.select().state(state_new).read()
                    joined_users = [s.data for s in new_samples if s.info.valid]
                    if joined_users:
                        self.handlers.users_joined(joined_users)
                    
                    # Users dropped
                    dropped_samples = self.reader_user.select().state(dds.InstanceState.NOT_ALIVE_MASK).take()
                    dropped_users = [s.data for s in dropped_samples if s.info.valid]
                    if dropped_users:
                        self.handlers.users_dropped(dropped_users)

    def _message_monitor(self):
        while True:
            active = self.waitset_msg.wait(dds.Duration(1))
            for cond in active:
                if cond == self.stop_condition:
                    return
                if cond == self.readcond_msg:
                    samples = self.reader_msg.select().state(dds.DataState(dds.SampleState.NOT_READ, dds.ViewState.ANY, dds.InstanceState.ALIVE)).read()
                    data = [s.data for s in samples if s.info.valid]
                    if data:
                        self.handlers.message_received(data)
