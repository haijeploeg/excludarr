from enum import Enum


class Action(str, Enum):
    delete = "delete"
    not_monitored = "not-monitored"
