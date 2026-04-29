"""Exceptions for IR transport routing (climate layer catches and surfaces)."""


from homeassistant.exceptions import HomeAssistantError


class IRRoutingMisconfigured(HomeAssistantError):
    """The configured ir_provider cannot operate (missing options or invalid hex pack).

    Raised when resolving or sending IR for an entry configured for Tuya (or explicitly
    mis-specified); never triggers a different IR backend — the failure is surfaced to logs.
    """

