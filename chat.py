
# WARNING: THIS FILE IS AUTO-GENERATED. DO NOT MODIFY.

# This file was generated from chat.idl
# using RTI Code Generator (rtiddsgen) version 4.6.0.
# The rtiddsgen tool is part of the RTI Connext DDS distribution.
# For more information, type 'rtiddsgen -help' at a command shell
# or consult the Code Generator User's Manual.

from dataclasses import field
from typing import Union, Sequence, Optional
import rti.idl as idl
import rti.rpc as rpc
from enum import IntEnum
import sys
import os
from abc import ABC



MAX_NAME_SIZE = 128

MAX_MSG_SIZE = 512

@idl.struct(
    type_annotations = [idl.xtypes_compliance(0x0000018C), ],

    member_annotations = {
        'username': [idl.key, idl.bound(MAX_NAME_SIZE),],
        'group': [idl.bound(MAX_NAME_SIZE),],
        'firstName': [idl.bound(MAX_NAME_SIZE),],
        'lastName': [idl.bound(MAX_NAME_SIZE),],
    }
)
class ChatUser:
    username: str = ""
    group: str = ""
    firstName: Optional[str] = None
    lastName: Optional[str] = None

@idl.struct(
    type_annotations = [idl.xtypes_compliance(0x0000018C), ],

    member_annotations = {
        'fromUser': [idl.bound(MAX_NAME_SIZE),],
        'toUser': [idl.bound(MAX_NAME_SIZE),],
        'toGroup': [idl.bound(MAX_NAME_SIZE),],
        'message': [idl.bound(MAX_MSG_SIZE),],
    }
)
class ChatMessage:
    fromUser: str = ""
    toUser: str = ""
    toGroup: str = ""
    message: str = ""
    timestamp_ms: int = 0
