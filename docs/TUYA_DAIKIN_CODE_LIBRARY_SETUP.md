# Tuya Daikin Code-Library Setup

This path is only for Daikin AC control through Tuya's official IR AC code
library. It does not use AeroState's Broadlink packs, LG protocol packs, LG
Tuya learned raw-code packs, or `localtuya_rc` learning.

## What This Route Supports

- Power on/off
- HVAC mode: cool, heat, auto, fan only, dry
- Temperature: 16C to 30C
- Fan: auto, low, medium, high

Swing, turbo, sleep, and other special Daikin buttons are intentionally hidden
for this route until they are verified for the selected Tuya Daikin remote
profile. Tuya's AC command API supports simple AC commands, while Daikin is
not a good fit for Tuya's multi-condition AC command path.

Tuya references:

- AC API overview: https://developer.tuya.com/en/docs/iot/air?id=K9wjmq6at6akq
- IR AC cloud APIs: https://developer.tuya.com/en/docs/cloud/infrared-air-conditioner-apis?id=Kb3oe9ehg02fn

## Required Tuya Setup

1. Add the Tuya IR blaster to the Tuya/Smart Life app.
2. Add an AC remote for brand `Daikin`.
3. Test the virtual remote in the Tuya app:
   - Power off
   - Power on
   - Cool 24C
   - Fan high
   - One extra mode you care about, such as dry or heat
4. In the Tuya IoT Platform, link the same app account to a cloud project.
5. Get these values from the Tuya project/API Explorer:
   - Tuya OpenAPI endpoint for your project data center
   - Access ID
   - Access Secret
   - `infrared_id` for the IR blaster
   - `remote_id` for the Daikin AC virtual remote

Common endpoints:

- India: `https://openapi.tuyain.com`
- United States: `https://openapi.tuyaus.com`
- Europe: `https://openapi.tuyaeu.com`
- China: `https://openapi.tuyacn.com`

## AeroState Setup

1. Go to Home Assistant Settings > Devices & services > Add integration.
2. Choose `AeroState`.
3. Select `Tuya Cloud code library (Daikin)`.
4. Enter:
   - Tuya OpenAPI endpoint
   - Tuya Access ID
   - Tuya Access Secret
   - Tuya IR device ID / `infrared_id`
   - Daikin AC remote ID / `remote_id`
   - Pack: `tuya_cloud.daikin_ac.v1`
5. Submit the confirmation step.
6. Open the created climate entity and test:
   - Turn off
   - Turn on cool 24C
   - Change temperature by 1C
   - Change fan mode
   - Change HVAC mode

## Reliability Notes

This route is usually more reliable than learned IR because Tuya owns the
Daikin code profile and keeps state for the virtual remote. It is still IR, so
there is no confirmation from the physical AC. A successful cloud response
means Tuya accepted the command for the IR blaster; it does not prove the AC
received it.

Expected reliability after the correct Daikin remote profile is selected:

- Basic power/temp/mode/fan: good
- Swing/special modes: not exposed yet
- Exact AC state after someone uses the original Daikin remote: assumed only

## File Boundaries

The Daikin code-library path lives in:

- `custom_components/aerostate/providers/tuya_cloud_ac.py`
- `custom_components/aerostate/packs/tuya_cloud/`

Existing LG paths remain separate:

- Broadlink/LG built-in packs: `custom_components/aerostate/packs/builtin/lg/`
- Tuya/LG learned or raw packs: `custom_components/aerostate/packs/tuya/`
- Tuya/LG raw-code library: `custom_components/aerostate/packs/tuya/raw_codes/`

