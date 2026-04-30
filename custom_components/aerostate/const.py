"""Constants for the AeroState integration."""

DOMAIN = "aerostate"
CONF_BROADLINK_ENTITY = "broadlink_entity"
CONF_BRAND = "brand"
CONF_MODEL_PACK = "model_pack"
CONF_TEMP_SENSOR = "temperature_sensor"
CONF_HUM_SENSOR = "humidity_sensor"
CONF_POWER_SENSOR = "power_sensor"
CONF_AREA = "area"
CONF_NAME = "name"
DEFAULT_NAME = "AeroState AC"

CONF_IR_PROVIDER = "ir_provider"
CONF_TUYA_IR_ENTITY = "tuya_ir_entity"
CONF_TUYA_MODEL_PACK = "tuya_model_pack"

CONF_IR_CONVERSION_ENABLED = "ir_conversion_enabled"

CONF_TUYA_IR_NO_ACK_MODE = "tuya_ir_no_ack_mode"
CONF_TUYA_LOCAL_DEVICE_ID = "tuya_local_device_id"
CONF_TUYA_IR_DP = "tuya_ir_dp"
CONF_TUYA_IR_SEND_BLOCKING = "tuya_ir_send_blocking"

DEFAULT_TUYA_IR_DP = 201

IR_PROVIDER_BROADLINK = "broadlink"
IR_PROVIDER_TUYA = "tuya"
DEFAULT_IR_PROVIDER = IR_PROVIDER_BROADLINK
