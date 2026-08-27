from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    waiting_team_code = State()
    waiting_leader_choice = State()


class EquipmentSetup(StatesGroup):
    choosing_drone = State()
    generator_serial = State()
    generator_hours = State()
    generator_last_oil_hours = State()
    battery1_serial = State()
    battery1_cycles = State()
    battery2_serial = State()
    battery2_cycles = State()
    battery3_serial = State()
    battery3_cycles = State()
    vehicle_manufacturer = State()
    vehicle_plate = State()
    vehicle_vin = State()
    vehicle_mileage = State()
    vehicle_last_oil_km = State()


class ReportFlow(StatesGroup):
    choosing_drone = State()
    choosing_work_type = State()
    entering_work_type_custom = State()
    entering_location = State()
    entering_area = State()
    entering_note = State()
    collecting_media = State()


class UpdateFlow(StatesGroup):
    waiting_value = State()


class PromoteFlow(StatesGroup):
    waiting_id = State()
