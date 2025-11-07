# PT Management Dashboard - Visual Layout

## Dashboard Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ PT Management                                                   👤 ptadmin   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  Statistics Cards                                                            │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │    Users     │ │ Containers   │ │   Running    │ │   Stopped    │       │
│  │      12      │ │       8      │ │       8      │ │       0      │       │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘       │
│                                                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│ USERS MANAGEMENT                                                             │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Users Management                    [Create User] [Bulk Create] [Delete] │ │
│ ├─────────────────────────────────────────────────────────────────────────┤ │
│ │ Username       │ Connections │ Actions          │                         │
│ │ student01      │ 1           │ [Delete]         │                         │
│ │ student02      │ 1           │ [Delete]         │                         │
│ │ student03      │ 1           │ [Delete]         │                         │
│ │ ptadmin        │ 2           │ [Delete]         │                         │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│ CONTAINERS                                                                   │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ Containers                                          [Create Instance]    │ │
│ ├─────────────────────────────────────────────────────────────────────────┤ │
│ │ Name          │ Status  │ Image │ Ports        │ Actions              │  │
│ │ ptvnc1        │ Running │ ptvnc │ 5901 5902... │ [View] [Stop]        │  │
│ │ ptvnc2        │ Running │ ptvnc │ 5901 5902... │ [View] [Stop]        │  │
│ │ ptvnc3        │ Running │ ptvnc │ 5901 5902... │ [View] [Stop]        │  │
│ │ ptvnc6        │ Running │ ptvnc │ 5901 5902... │ [View] [Stop]        │  │
│ │ ptvnc7        │ Running │ ptvnc │ 5901 5902... │ [View] [Stop]        │  │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Modal 1: Create Instance

```
┌─────────────────────────────────────────────────────────────┐
│ ✕ Create New ptvnc Instance                                 │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Container Name                                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ ptvnc8                                                │  │
│  └───────────────────────────────────────────────────────┘  │
│  Leave empty for auto-numbered (ptvnc3, ptvnc4, etc.)      │
│                                                              │
│  [✓] SUCCESS: Container created successfully!              │
│      (Optional success/error message appears here)          │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│  [Cancel]                      [⚙ Create Instance]          │
└─────────────────────────────────────────────────────────────┘
```

**What happens:**
1. User enters container name
2. Clicks "Create Instance"
3. Container is created via Docker API
4. Container is **automatically registered** in Guacamole
5. Success message shows connection ID and name
6. Modal closes and containers list refreshes

---

## Modal 2: Create User & Assign Container

```
┌──────────────────────────────────────────────────────────────┐
│ ✕ Create User & Assign Container                             │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  Username                                                    │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ student01                                              │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                               │
│  Password                                                    │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ ••••••••••                                             │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                               │
│  Assign Container                                            │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ ptvnc1 (Running)                                ▼     │ │
│  │ -- Select a container --                               │ │
│  │ ptvnc1 (Running)                                       │ │
│  │ ptvnc2 (Running)                                       │ │
│  │ ptvnc3 (Running)                                       │ │
│  │ ptvnc4 (Running)                                       │ │
│  │ ptvnc6 (Running)                                       │ │
│  │ ptvnc7 (Running)                                       │ │
│  └────────────────────────────────────────────────────────┘ │
│  User will have access to the selected container            │
│                                                               │
│  [✓] User created and assigned successfully!                │
│      (Optional success/error message appears here)          │
│                                                               │
├──────────────────────────────────────────────────────────────┤
│  [Cancel]                         [✓ Create User]            │
└──────────────────────────────────────────────────────────────┘
```

**What happens:**
1. User enters username and password
2. Selects container from dropdown
3. Clicks "Create User"
4. User is created in Guacamole database
5. Container is assigned to user
6. Success message confirms assignment
7. Modal closes and users list refreshes

---

## Modal 3: Bulk Create (Updated)

```
┌──────────────────────────────────────────────────────────────┐
│ ✕ Bulk Create Users                                          │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  CSV File                                                    │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Choose File    students.csv                       [x]  │ │
│  └────────────────────────────────────────────────────────┘ │
│  Format: username,password                                  │
│                                                               │
│  ☐ Create New Containers Per User                          │
│    ✓ Creates a new container for each user                 │
│    ✓ Assigns container to the user                         │
│    ✓ Containers auto-start on creation                     │
│                                                               │
│  OR Assign Existing Container                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ -- No assignment --                               ▼    │ │
│  │ ptvnc1 (Running)                                       │ │
│  │ ptvnc2 (Running)                                       │ │
│  │ ptvnc3 (Running)                                       │ │
│  └────────────────────────────────────────────────────────┘ │
│  Applied to all users if checkbox above is unchecked        │
│                                                               │
│  Preview (first 5 rows):                                    │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ Username    │ Password │                                │ │
│  │ student01   │ •••••••• │                                │ │
│  │ student02   │ •••••••• │                                │ │
│  │ student03   │ •••••••• │                                │ │
│  │ student04   │ •••••••• │                                │ │
│  │ student05   │ •••••••• │                                │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                               │
├──────────────────────────────────────────────────────────────┤
│  [Cancel]                           [Create Users]           │
└──────────────────────────────────────────────────────────────┘
```

---

## Data Flow Diagram

### Create Instance Flow

```
Dashboard
    ↓
[Create Instance Button Click]
    ↓
Create Instance Modal Opens
    ↓
User Enters Container Name
    ↓
User Clicks "Create Instance" Button
    ↓
POST /api/containers
    ↓
┌─────────────────────────────────┐
│ Backend (pt-management)         │
├─────────────────────────────────┤
│ 1. Create container via Docker  │
│    - Mount shared volumes       │
│    - Set environment vars       │
│    - Expose VNC port 5901       │
│                                  │
│ 2. Auto-register in Guacamole   │
│    - Generate connection name   │
│    - Create VNC connection      │
│    - Set proxy settings         │
│    - Grant permissions to admin │
│                                  │
│ 3. Return connection_id         │
└─────────────────────────────────┘
    ↓
Response with connection_name & connection_id
    ↓
Success Message Displayed
    ↓
Container Appears in:
├─ Docker (running)
├─ Guacamole UI (new connection)
├─ pt-management dashboard (containers list)
└─ Available in dropdown for user assignment
```

---

### Create User & Assign Container Flow

```
Dashboard
    ↓
[Create User Button Click]
    ↓
Create User Modal Opens
    ↓
User Fills Form:
├─ Username
├─ Password
└─ Select Container (dropdown)
    ↓
User Clicks "Create User" Button
    ↓
POST /api/users
    ↓
┌──────────────────────────────────┐
│ Backend (pt-management)          │
├──────────────────────────────────┤
│ 1. Create user in Guacamole      │
│                                   │
│ 2. Assign container to user      │
│    - Insert into user_container  │
│      _mapping table              │
│    - Grant READ permission on    │
│      VNC connection              │
│                                   │
│ 3. Return success status         │
└──────────────────────────────────┘
    ↓
Response confirms user created & assigned
    ↓
Success Message Displayed
    ↓
User Can Now:
├─ Log in to pt-management
├─ See assigned container in Guacamole
├─ Launch remote desktop session
└─ Access Packet Tracer
```

---

### Bulk Create Flow

```
Dashboard
    ↓
[Bulk Create Button Click]
    ↓
Bulk Create Modal Opens
    ↓
User Selects CSV File
    ↓
CSV Preview Shows First 5 Rows
    ↓
User Selects Option:
├─ Create New Containers Per User
│   └─ Each user gets own container
└─ Assign Existing Container
    └─ All users get same container
    ↓
User Clicks "Create Users" Button
    ↓
For Each User in CSV:
│
├─ POST /api/containers (if create_container=true)
│   └─ Creates new container
│       └─ Auto-registers in Guacamole
│
└─ POST /api/users
    └─ Creates user
    └─ Assigns to container
    ↓
Bulk Response Shows:
├─ Users created: N
├─ Containers created: N
└─ Failed: N
    ↓
All Users Appear in Dashboard
All Containers Available in Guacamole
```

---

## Component Interaction

```
PT Management Dashboard
│
├─── Users Section
│    ├─ [Create User] ──→ Modal with container dropdown
│    ├─ [Bulk Create] ──→ Modal with CSV upload
│    │                  └─ Populates container dropdown
│    └─ User List ──→ Shows assigned containers
│
├─── Containers Section
│    ├─ [Create Instance] ──→ Modal with name input
│    │                      └─ Auto-registers in Guacamole
│    └─ Container List ──→ Shows running containers
│                          └─ Auto-populated in user modals
│
└─── Statistics
     ├─ Total Users (from guacamole_user table)
     ├─ Total Containers (from Docker)
     ├─ Running (from Docker stats)
     └─ Stopped (from Docker stats)
```

---

## Workflow Example: Deploy 40 Students

```
Step 1: Create CSV file (students.csv)
─────────────────────────────────────
username,password
student01,Welcome@2025
student02,Welcome@2025
... (40 rows total)

Step 2: Open PT Management Dashboard
──────────────────────────────────────
Navigate to http://pt-management:5000
Login as ptadmin/IlovePT

Step 3: Bulk Create Users
──────────────────────────
1. Click [Bulk Create] button
2. Upload students.csv
3. Check "Create New Containers Per User"
4. Click [Create Users]

Result After 2-3 minutes:
───────────────────────
✓ 40 users created
✓ 40 containers created (ptvnc8 to ptvnc47)
✓ 40 auto-registered in Guacamole
✓ All containers running
✓ All students can access their container

Students can now:
─────────────────
1. Go to http://guacamole:8080
2. Login with username/password
3. See their assigned Packet Tracer container
4. Launch remote session
5. Start working on Packet Tracer labs
```

---

## Success Indicators

### Container Created Successfully
- ✅ Container appears in `docker ps`
- ✅ Container appears in Guacamole UI
- ✅ Container has VNC connection entry in database
- ✅ Connection name follows naming convention (pt01, pt02, etc.)
- ✅ Proxy settings configured correctly

### User Created Successfully
- ✅ User appears in users list
- ✅ User has connection permission in Guacamole
- ✅ User can see assigned container
- ✅ Entry in user_container_mapping table

### Bulk Deployment Successful
- ✅ All users created with correct passwords
- ✅ All containers created if "Create New" option selected
- ✅ All users assigned to containers
- ✅ Users list shows all new users
- ✅ Container list shows all new containers
