import os
import threading
import logging
from typing import Callable, List
from collections import deque

import rti.connextdds as dds
from generated.chat import ChatUser, ChatMessage


class Handlers:
    """Callbacks the GUI/application may set."""
    users_joined: Callable[[List[ChatUser]], None] = lambda *_: logging.warning("Not implemented")
    users_dropped: Callable[[List[ChatUser]], None] = lambda *_: logging.warning("Not implemented")
    message_received: Callable[[List[ChatMessage]], None] = lambda *_: logging.warning("Not implemented")


class DDSApp:
    """DDS application for chat messaging, to be driven from the application code."""

    TOPIC_NAME_USER = "userInfo"
    TOPIC_NAME_MSG = "message"
    QOS_PROVIDER_XML = os.path.join(os.path.dirname(__file__), "chat_qos.xml")
    QOS_LIBRARY = "Chat_Library"
    QOS_PROFILE_USER = "ChatUser_Profile"
    QOS_PROFILE_MSG = "ChatMessage_Profile"

    def __init__(self, user: ChatUser, handlers=Handlers(), auto_join=True, domain_id=0):
        """Create the DDS entities and start monitor threads."""
        self.user = user

        # Pre-allocate a message sample we reuse when sending
        self.message = ChatMessage()
        self.message.fromUser = self.user.username
        self.history = deque(maxlen=500)
        self.handlers = handlers

        # ---- DomainParticipant (uses participant QoS from XML) ----
        # If you later enable Security, we’ll create the participant with properties here.
        self.qos_provider = dds.QosProvider(self.QOS_PROVIDER_XML)
        pqos = self.qos_provider.participant_qos_from_profile(f"{self.QOS_LIBRARY}::Chat_Profile")
        self.participant = dds.DomainParticipant(domain_id, pqos)
     
        # A guard condition to stop WaitSets when leaving
        self.stop_condition = dds.GuardCondition()

        # ---- ChatUser topic: presence / liveliness ----
        self.topic_user = dds.Topic(self.participant, self.TOPIC_NAME_USER, ChatUser)
        qos_profile_user = f"{self.QOS_LIBRARY}::{self.QOS_PROFILE_USER}"
        self.writer_user = dds.DataWriter(
            self.topic_user,
            qos=self.qos_provider.datawriter_qos_from_profile(qos_profile_user),
        )
        self.reader_user = dds.DataReader(
            self.topic_user,
            qos=self.qos_provider.datareader_qos_from_profile(qos_profile_user),
        )

        # ReadCondition for "new and alive" samples
        self.readcond_user = dds.ReadCondition(
            self.reader_user,
            dds.DataState(dds.SampleState.NOT_READ, dds.ViewState.ANY, dds.InstanceState.ANY),
        )
        self.waitset_user = dds.WaitSet()
        self.waitset_user.attach_condition(self.stop_condition)
        self.waitset_user.attach_condition(self.readcond_user)

        self.thread_user = threading.Thread(target=self._user_monitor, daemon=True)
        self.thread_user.start()

        # ---- ChatMessage topic: partitions per group + content filter ----
        self.topic_msg = dds.Topic(self.participant, self.TOPIC_NAME_MSG, ChatMessage)
        qos_profile_msg = f"{self.QOS_LIBRARY}::{self.QOS_PROFILE_MSG}"

        # Publisher/Subscriber with partitions based on the user's group
        self.pub_msg = dds.Publisher(self.participant)
        self._set_partition(self.pub_msg, self.user.group)

        self.sub_msg = dds.Subscriber(self.participant)
        self._set_partition(self.sub_msg, self.user.group)

        self.writer_msg = dds.DataWriter(
            self.pub_msg,
            self.topic_msg,
            qos=self.qos_provider.datawriter_qos_from_profile(qos_profile_msg),
        )

        # Receive only DMs to me OR messages to my group
        filter_expression = "toUser = %0 OR toGroup = %1"
        filter_parameters = [f"'{self.user.username}'", f"'{self.user.group}'"]
        self.reader_cft = dds.ContentFilteredTopic(
            self.topic_msg,
            "FilterByUsernameOrGroup",
            dds.Filter(filter_expression, filter_parameters),
        )
        self.reader_msg = dds.DataReader(
            self.sub_msg,
            self.reader_cft,
            qos=self.qos_provider.datareader_qos_from_profile(qos_profile_msg),
        )
        self.readcond_msg = dds.ReadCondition(
            self.reader_msg,
            dds.DataState(dds.SampleState.NOT_READ, dds.ViewState.ANY, dds.InstanceState.ANY)
        )

        print("[QOS] writer durability:", self.writer_msg.qos.durability.kind)
        print("[QOS] reader durability:", self.reader_msg.qos.durability.kind)


        self.waitset_msg = dds.WaitSet()

        self.waitset_msg.attach_condition(self.stop_condition)
        self.waitset_msg.attach_condition(self.readcond_msg)

        self.load_history()

        self.thread_msg = threading.Thread(target=self._message_monitor, daemon=True)
        self.thread_msg.start()

        # Announce presence as soon as we start
        if auto_join:
            self.user_join()
      
            

    # ---------- Public API ----------

    def user_join(self):
        """Publish our user info so others see we joined."""
        self.writer_user.write(self.user)

    def user_update_group(self, group: str):
        """Change this user's group; update partitions and filters accordingly."""
        self.user.group = group
        self._set_partition(self.pub_msg, self.user.group)
        self._set_partition(self.sub_msg, self.user.group)
        self.reader_cft.filter_parameters = [f"'{self.user.username}'", f"'{self.user.group}'"]
        self.writer_user.write(self.user)

    def user_list(self):
        """Return the current 'userInfo' samples known to our reader."""
        return self.reader_user.read_data()

    def message_send(self, destination: str, message: str):
        """Send to either a user (DM) or the whole group (fixed routing)."""
        self.message.message = message
        if destination == self.user.group:
            # Group message
            self.message.toUser = ""
            self.message.toGroup = self.user.group
        else:
            # Direct message to a user
            self.message.toUser = destination
            self.message.toGroup = ""
        self.writer_msg.write(self.message)

    def user_leave(self):
        """Gracefully shut down: unregister user and stop threads."""
        if self.participant.closed:
            return

        # Unregister ourselves on the user topic
        instance_handle = self.writer_user.lookup_instance(self.user)
        if instance_handle:
            self.writer_user.unregister_instance(instance_handle)

        # Wake up waitsets and join monitor threads
        self.stop_condition.trigger_value = True
        self.thread_user.join()
        self.thread_msg.join()

        # Detach conditions and close entities
        self.waitset_user.detach_all()
        self.waitset_msg.detach_all()
        self.participant.close_contained_entities()
        self.participant.close()

    def load_history(self):
        """
        Deliver any historical samples (from Persistence Service) once at startup.
        We TAKE them so they won't be delivered again by the background thread.
        Returns the list of ChatMessage samples delivered.
        """
        # We only care about 'alive' data; samples arrive as NOT_READ initially
        state = dds.DataState(dds.SampleState.NOT_READ, dds.ViewState.ANY, dds.InstanceState.ALIVE)

        # TAKE first
        samples = self.reader_msg.select().state(state).take_data()
        
        print(f"[HISTORY] persisted samples at join: {len(samples) if samples else 0}")
        
        # Append them to in-memory history
        for s in samples:
            dest = s.toUser if s.toUser else (s.toGroup if s.toGroup else self.user.group)
            self.history.append((s.fromUser, dest, s.message))

        # Then notify GUI / app
        if samples:
            self.handlers.message_received(samples)

        return samples


    # ---------- Helpers & monitors ----------

    def _set_partition(self, pubsub, partition_name: str):
        """Helper to set the Partition QoS on a Publisher or Subscriber."""
        qos = pubsub.qos
        qos.partition.name = [partition_name]
        pubsub.qos = qos

    def _user_monitor(self):
        """Background: watch the user topic for joins/drops and call handlers."""
        while True:
            active = self.waitset_user.wait(dds.Duration(1))
            for cond in active:
                if cond == self.stop_condition:
                    return
                if cond == self.readcond_user:
                    # New/updated alive users
                    state_alive = dds.DataState(
                        dds.SampleState.NOT_READ, dds.ViewState.ANY, dds.InstanceState.ALIVE
                    )
                    new_samples = self.reader_user.select().state(state_alive).read_data()
                    if new_samples:
                        self.handlers.users_joined(new_samples)

                    # Dropped users (unregistered / not alive)
                    dropped = self.reader_user.select().state(dds.InstanceState.NOT_ALIVE_MASK).take_data()
                    if dropped:
                        self.handlers.users_dropped(dropped)

    def _message_monitor(self):
        """Background: receive new messages and call the handler."""
        while True:
            active = self.waitset_msg.wait(dds.Duration(1))
            for cond in active:
                if cond == self.stop_condition:
                    return
                if cond == self.readcond_msg:
                    samples = self.reader_msg.take_data()
                    if samples:
                        # Save each message into the in-memory history
                        for s in samples:
                            dest = s.toUser if s.toUser else (s.toGroup if s.toGroup else self.user.group)
                            self.history.append((s.fromUser, dest, s.message))

                        # Then notify the GUI / main app
                        self.handlers.message_received(samples)
                        
    def search_history(self, term: str):
        t = term.lower()
        return [h for h in self.history if t in (h[0].lower() + " " + (h[1] or "") + " " + h[2].lower())]

