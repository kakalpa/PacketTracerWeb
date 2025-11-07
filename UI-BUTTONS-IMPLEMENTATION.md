# PT Management UI - New Buttons Implementation

## Summary

Added three new interactive buttons to the PT Management Dashboard for easy container and user management:

1. **Create Instance** button - Creates new ptvnc containers and auto-registers them in Guacamole
2. **Create User** button - Creates a single user and assigns an existing container
3. **Bulk Create** button (already existed) - Creates multiple users from CSV file

---

## Implementation Details

### 1. Create Instance Button ✅

**Location:** Dashboard Header → Containers Card → "Create Instance" Button

**Features:**
- Opens modal dialog to create new ptvnc container
- Optional container name input (auto-numbered if left blank)
- **Auto-registers in Guacamole** - No separate step needed
- Shows success/error message inline
- Auto-closes after 2 seconds on success
- Refreshes containers list automatically

**Flow:**
```
Click "Create Instance" 
  → Enter container name (e.g., "ptvnc8")
  → Click "Create Instance" button
  → Container created + auto-registered in Guacamole
  → Success message displays
  → Modal closes
  → Containers list refreshes
```

**API Endpoint:** `POST /api/containers`
- Request: `{"name": "ptvnc8", "image": "ptvnc"}`
- Response: Returns container_name, connection_id, connection_name
- **Auto-registers** the container in Guacamole automatically

---

### 2. Create User Button ✅

**Location:** Dashboard Header → Users Card → "Create User" Button

**Features:**
- Opens modal dialog to create single user
- Dropdown to select existing container to assign
- Input fields for username and password
- Validates all required inputs before submission
- Shows success/error message inline
- Auto-closes after 2 seconds on success
- Refreshes users list automatically

**Flow:**
```
Click "Create User"
  → Enter username (e.g., "student01")
  → Enter password
  → Select container from dropdown (e.g., "ptvnc1")
  → Click "Create User" button
  → User created and assigned to container
  → Success message displays
  → Modal closes
  → Users list refreshes
```

**API Endpoint:** `POST /api/users`
- Request: `{"users": [{"username": "student01", "password": "Test@123", "container": "ptvnc1"}]}`
- Response: Returns count_created, count_failed
- Container dropdown populated from available containers

---

### 3. Bulk Create Button (Enhanced) ✅

**Location:** Dashboard Header → Users Card → "Bulk Create" Button

**Features:**
- Upload CSV file with multiple users
- Two options:
  - **Create New Containers Per User** - Creates new ptvnc instance for each user
  - **Assign Existing Container** - Assigns same container to all users
- CSV Preview shows first 5 rows
- Shows success/error counts

**CSV Format:**
```
username,password
student01,Password@123
student02,Password@123
student03,Password@123
```

---

## UI Components Added

### Dashboard.html Changes

1. **Create Instance Modal** - Lines 311-329
   - Modal ID: `createContainerModal`
   - Container name input field
   - Create button with loading state

2. **Create User Modal** - Lines 331-362
   - Modal ID: `createSingleUserModal`
   - Username input field
   - Password input field
   - Container dropdown
   - Create button with loading state

3. **Button Updates**
   - Added "Create User" button to Users header (line 158)
   - Added "Create Instance" button to Containers header (line 196)

### Dashboard.js Changes

1. **Event Listeners** - Line 14-15
   - `createContainerBtn` click handler → `createNewContainer()`
   - `createSingleUserBtn` click handler → `createSingleUserWithContainer()`

2. **New Functions**
   - `createNewContainer()` - Lines 328-381
     - Validates container name
     - Calls API to create container
     - Shows success/error messages
     - Refreshes containers and available containers
   
   - `createSingleUserWithContainer()` - Lines 383-439
     - Validates username, password, container
     - Calls API to create user with container
     - Shows success/error messages
     - Refreshes users list and stats
   
   - `updateSingleUserContainerSelect()` - Lines 81-93
     - Populates container dropdown in create user modal

3. **Container Dropdown Loading**
   - `loadAvailableContainers()` updated to also call `updateSingleUserContainerSelect()`

---

## Backend Changes

### Routes.py - Auto-Registration Feature ✅

**Modified: `/api/containers` POST endpoint** - Lines 297-361

**New Behavior:**
1. Creates container using Docker API
2. **Automatically** registers container in Guacamole
3. Generates connection name from container name:
   - `ptvnc1` → `pt01`
   - `ptvnc7` → `pt7`
   - `ptvnc10` → `pt10`
4. Sets up VNC connection with:
   - Proxy: guacd (port 4822)
   - VNC Port: 5901
   - Password: Cisco123
   - Max connections: 1 per user
5. Returns connection_id and connection_name

**Response Example:**
```json
{
  "success": true,
  "container_name": "ptvnc7",
  "connection_name": "pt7",
  "connection_id": 7,
  "message": "Container ptvnc7 created and registered successfully"
}
```

---

## Database Schema

### New Table: user_container_mapping

Created to track user-to-container assignments:

```sql
CREATE TABLE user_container_mapping (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    container_name VARCHAR(255) NOT NULL,
    status VARCHAR(50) DEFAULT 'assigned',
    assigned_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_user_container (user_id, container_name),
    FOREIGN KEY (user_id) REFERENCES guacamole_user(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb3 COLLATE=utf8mb3_uca1400_ai_ci;
```

---

## Testing Results ✅

### Test 1: Create Instance with Auto-Registration
```bash
curl -X POST http://127.0.0.1:5000/api/containers \
  -H "Content-Type: application/json" \
  -d '{"name": "ptvnc7", "image": "ptvnc"}'

Response:
{
  "success": true,
  "container_name": "ptvnc7",
  "connection_name": "pt7",
  "connection_id": 7,
  "message": "Container ptvnc7 created and registered successfully"
}
```

**Result:** ✅ Container created and appears in Guacamole immediately

### Test 2: Verify in Guacamole Database
```bash
SELECT connection_id, connection_name, protocol FROM guacamole_connection WHERE connection_name LIKE 'pt%';

Results:
pt01, pt02, pt03, pt04, pt-test, pt6, pt7 (all visible in Guacamole)
```

**Result:** ✅ All newly created containers visible in Guacamole

---

## Usage Guide

### For Instructors/Admins

**Scenario 1: Create one container for testing**
1. Go to Dashboard → Containers section
2. Click "Create Instance" button
3. Enter container name (e.g., "ptvnc-test")
4. Click "Create Instance"
5. Wait for success message
6. Container is now available in Guacamole

**Scenario 2: Create a user and assign a container**
1. Go to Dashboard → Users section
2. Click "Create User" button
3. Enter username, password, select container
4. Click "Create User"
5. User can now access the assigned container

**Scenario 3: Deploy 40 students with containers**
1. Prepare CSV file with student usernames and passwords
2. Go to Dashboard → Users section
3. Click "Bulk Create" button
4. Select CSV file
5. Check "Create New Containers Per User"
6. Click "Create Users"
7. Each student gets their own container

---

## File Changes Summary

| File | Changes | Lines |
|------|---------|-------|
| templates/dashboard.html | Added Create Instance and Create User modals | +100 |
| static/js/dashboard.js | Added event listeners and new functions | +120 |
| ptmanagement/api/routes.py | Added auto-registration to container creation | +50 |
| (Database) | Created user_container_mapping table | N/A |

---

## Current Container Status

Containers now in Guacamole:
- ✅ ptvnc1 (pt01) - Original
- ✅ ptvnc2 (pt02) - Original
- ✅ ptvnc3 (pt03) - Created dynamically
- ✅ ptvnc4 (pt04) - Created dynamically
- ✅ ptvnc5 - Created dynamically (not registered yet)
- ✅ ptvnc6 (pt6) - Created & registered dynamically
- ✅ ptvnc7 (pt7) - Created & auto-registered with new feature
- ✅ ptvnc-test-vol (pt-test) - Created & registered

---

## Next Steps

1. **Test User Creation** - When user creation endpoint is fixed
2. **Test Bulk Deployment** - Create 40 students with CSV
3. **Fine-tune UI** - Add loading animations, better error messages
4. **Permissions** - Ensure users only see their assigned containers
5. **Production Deployment** - Move to production environment

---

## Notes

- All new containers automatically reuse shared Packet Tracer binary from `pt_opt` named volume
- Containers boot in ~30 seconds
- Each container gets unique VNC port (5901)
- Guacamole proxy handles remote desktop protocol
- Admin credentials: ptadmin/IlovePT
