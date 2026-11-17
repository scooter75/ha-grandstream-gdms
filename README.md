<p align="center">
  <img src="https://raw.githubusercontent.com/scooter75/ha-grandstream-gdms/main/docs/assets/grandstream.svg" alt="Grandstream Logo" width="140" />
</p>

# Grandstream GDMS for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/scooter75/ha-grandstream-gdms)](https://github.com/scooter75/ha-grandstream-gdms/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A custom Home Assistant integration for the **Grandstream Device Management System (GDMS) OpenAPI** (`oapi/v1.0.0`). It synchronizes your cloud-managed Grandstream endpoints (GRP/GXP/GXV IP phones, HT8xx ATAs, GDS door access, GWN networking) into Home Assistant devices with live diagnostics and remote management actions.

---

## Features

- **OAuth2 & SHA-256 Request Signing:** Implements the official GDMS API authentication (`SHA256(MD5(password))` grant + automatic token refresh) and per-request SHA-256 signature verification.
- **Multi-Region Cloud Support:**
  - World / Americas (`www.gdms.cloud`)
  - Europe (`eu.gdms.cloud`)
  - Oceania (`oc.gdms.cloud`)
- **Per-Device Entities:**
  - **Binary Sensor (`Connectivity`):** Online/offline state with MAC, serial number, model, firmware, and site attributes.
  - **Sensor (`SIP Registration`):** Live SIP account registration summary (`Registered (2/2)`, `Partial`, `Unregistered`, `Offline`) with full account details in attributes.
  - **Diagnostic Sensors:** Local IP address, Public IP address, Firmware Version, and GDMS Site.
  - **Action Buttons:** `Reboot` and `Push Configuration`.
- **Hub Fleet Sensors:** Total Devices, Online Devices, and Offline Devices.
- **Home Assistant Services:** `grandstream_gdms.reboot_device`, `grandstream_gdms.push_config`, and `grandstream_gdms.add_task`.

---

## Prerequisites: Enable GDMS API Developer Mode

1. Log in to your regional [GDMS Portal](https://www.gdms.cloud).
2. In the left navigation menu, go to **Others -> API Developer**.
3. Click **Apply for API Developer** (or **Activate**).
4. Record your **API Client ID** and **Secret Key**.

---

## Installation

### Option 1: HACS / Home Assistant Marketplace (Recommended)

1. Open **HACS** (or **Marketplace** in Home Assistant).
2. Click the three-dot menu (`⋮`) in the top-right corner and select **Custom repositories**.
3. Enter the repository URL:
   ```text
   https://github.com/scooter75/ha-grandstream-gdms
   ```
4. Select **Integration** as the category and click **Add**.
5. Search for **Grandstream GDMS**, click **Download**, and restart Home Assistant.

### Option 2: Manual Installation

1. Download the latest release from [`scooter75/ha-grandstream-gdms`](https://github.com/scooter75/ha-grandstream-gdms/releases).
2. Copy the `custom_components/grandstream_gdms` folder into your Home Assistant `config/custom_components/` directory.
3. Restart Home Assistant.

---

## Configuration

1. In Home Assistant, go to **Settings -> Devices & Services -> + Add Integration**.
2. Search for **Grandstream GDMS**.
3. Enter your:
   - **GDMS Regional Server** (`www.gdms.cloud`, `eu.gdms.cloud`, or `oc.gdms.cloud`)
   - **API Client ID** & **API Secret Key**
   - **GDMS Username** & **GDMS Password**
   - **Polling Interval** (default: `60` seconds)
4. If your account manages multiple GDMS organizations, select a specific organization or **All Organizations**.

---

## Services & Automation Examples

### Reboot a Phone Automatically When Unregistered

```yaml
automation:
  - alias: "Reboot Desk Phone if SIP Unregistered"
    trigger:
      - platform: state
        entity_id: sensor.reception_phone_sip_registration
        to: "Unregistered (0/1)"
        for:
          minutes: 10
    action:
      - service: grandstream_gdms.reboot_device
        data:
          mac: "00:0B:82:AA:BB:CC"
```

### Push Configuration Update via Service Call

```yaml
service: grandstream_gdms.push_config
data:
  device_id: YOUR_HOME_ASSISTANT_DEVICE_ID
```

---
  
