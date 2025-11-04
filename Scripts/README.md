# Test Scripts - GeoIP Filtering

This folder contains additional test scripts for validating GeoIP filtering logic and configuration.

## Available Scripts

### `test-nginx-geoip-logic.sh`
Tests the original GeoIP filtering logic (before v3).
- **Tests:** 5 scenarios
- **Purpose:** Validates basic blocking logic
- **Run:** `bash Scripts/test-nginx-geoip-logic.sh`

### `test-nginx-geoip-logic-v2.sh`
Tests GeoIP filtering with localhost exception.
- **Tests:** 7 scenarios
- **Purpose:** Validates localhost bypass logic
- **Run:** `bash Scripts/test-nginx-geoip-logic-v2.sh`

### `test-nginx-geoip-logic-v3.sh` ⭐ (Latest)
Tests GeoIP filtering with trusted IP bypass (current version).
- **Tests:** 13 scenarios
- **Purpose:** Validates trusted IP bypass for public IPs
- **Run:** `bash Scripts/test-nginx-geoip-logic-v3.sh`
- **Result:** All 13 tests PASS ✅

**Test Coverage:**
- Localhost access (127.x)
- Private network access (10.x, 172.x, 192.168.x)
- Public IP whitelist (allowed countries)
- Public IP blacklist (blocked countries)
- Unknown public IPs

### `test-nginx-config-preview.sh`
Displays a preview of the nginx configuration that will be generated.
- **Purpose:** Visual verification of GeoIP directives
- **Run:** `bash Scripts/test-nginx-config-preview.sh`
- **Output:** Shows map definitions, if-block logic, and scenario table

### `test-public-ip-detection.sh` ⭐
Tests the automatic public IP detection logic for production mode.
- **Tests:** 4 scenarios
- **Scenarios:**
  1. Development mode (local IPs only)
  2. Production mode with auto-detect
  3. Production mode with manual IP
  4. Production mode with custom override
- **Run:** `bash Scripts/test-public-ip-detection.sh`
- **Result:** All 4 scenarios PASS ✅

### `test-deploy-config-gen.sh`
Tests that deploy.sh correctly generates the nginx configuration.
- **Purpose:** Validates configuration generation from source
- **Run:** `bash Scripts/test-deploy-config-gen.sh`

### `verify-geoip-fix.sh`
Quick verification that the GeoIP fix is applied in deploy.sh.
- **Tests:** 2 checks
  1. ✅ Fixed logic is present: `if ($allowed_country != 1)`
  2. ✅ Old broken logic is removed: `if ($allowed_country = 0)`
- **Run:** `bash Scripts/verify-geoip-fix.sh`
- **Result:** VERIFICATION PASSED ✅

## Quick Test All

Run all GeoIP logic tests:

```bash
bash Scripts/test-nginx-geoip-logic.sh
bash Scripts/test-nginx-geoip-logic-v2.sh
bash Scripts/test-nginx-geoip-logic-v3.sh
bash Scripts/test-public-ip-detection.sh
bash Scripts/verify-geoip-fix.sh
```

## Integration with Main Tests

These scripts complement the main test suite:

- **`test-deployment.sh`** (root directory)
  - Full end-to-end deployment test (57 tests)
  - Tests all components together
  - Requires running Docker containers

- **GeoIP test scripts** (this folder)
  - Unit tests for specific logic
  - No Docker required
  - Fast local validation

## Test Results Summary

| Script | Tests | Status |
|--------|-------|--------|
| test-nginx-geoip-logic.sh | 5 | ✅ PASS |
| test-nginx-geoip-logic-v2.sh | 7 | ✅ PASS |
| test-nginx-geoip-logic-v3.sh | 13 | ✅ PASS |
| test-public-ip-detection.sh | 4 | ✅ PASS |
| verify-geoip-fix.sh | 2 | ✅ PASS |
| **Total** | **31** | **✅ ALL PASS** |

## Documentation

For detailed information about GeoIP filtering, see:

- `../Documents/GEOIP-FIX-SUMMARY.md` - Quick reference of all fixes
- `../Documents/GEOIP-FIX-TEST-REPORT.md` - Detailed test report
- `../Documents/VPS-DEPLOYMENT-GUIDE.md` - VPS deployment guide
- `../README.md` - General project documentation
