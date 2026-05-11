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
CONF_TUYA_DEVICE_NAME = "tuya_device_name"
CONF_TUYA_MODEL_PACK = "tuya_model_pack"
DEFAULT_TUYA_DEVICE_NAME = "Living AC IR"

CONF_TUYA_CLOUD_ENDPOINT = "tuya_cloud_endpoint"
CONF_TUYA_CLOUD_ACCESS_ID = "tuya_cloud_access_id"
CONF_TUYA_CLOUD_ACCESS_SECRET = "tuya_cloud_access_secret"
CONF_TUYA_INFRARED_ID = "tuya_infrared_id"
CONF_TUYA_REMOTE_ID = "tuya_remote_id"
CONF_TUYA_CLOUD_MODEL_PACK = "tuya_cloud_model_pack"
DEFAULT_TUYA_CLOUD_ENDPOINT = "https://openapi.tuyain.com"

CONF_IR_CONVERSION_ENABLED = "ir_conversion_enabled"

IR_PROVIDER_BROADLINK = "broadlink"
IR_PROVIDER_TUYA = "tuya"
IR_PROVIDER_TUYA_CLOUD = "tuya_cloud"
DEFAULT_IR_PROVIDER = IR_PROVIDER_BROADLINK
