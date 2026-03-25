"""FSM states for the bot."""
from aiogram.fsm.state import State, StatesGroup


class MenuState(StatesGroup):
    """State for storing selected menu section."""
    selected_section = State()


class FeedbackState(StatesGroup):
    """State for awaiting feedback comment."""
    awaiting_comment = State()
    awaiting_other_comment = State()  # v1.1: for "other" reason comment


class SpecialistRequest(StatesGroup):
    """States for specialist consultation request flow."""
    city = State()
    property_type = State()
    request_type = State()  # v1.1: renamed from goal, but keep goal for backward compatibility
    goal = State()  # Keep for backward compatibility, but use request_type in data
    budget = State()  # v1.1: new field
    urgency = State()  # v1.1: new field
    details = State()