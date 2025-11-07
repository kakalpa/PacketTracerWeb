# PT Management Dashboard - Quick Reference

## Three Ways to Create Containers & Users

### Method 1: Create Instance Button (Quickest)

**Best for:** Creating test containers, adding more containers on demand

```
Dashboard → Containers → [Create Instance]
  ↓
Enter container name: ptvnc9
  ↓
Click [Create Instance]
  ↓
✓ Container created AND registered in Guacamole instantly
```

**Result:** 
- Container is immediately available in Guacamole
- No manual registration step needed
- Can be assigned to users later

---

### Method 2: Create User Button (Single User)

**Best for:** Creating one student account, onboarding individual users

```
Dashboard → Users → [Create User]
  ↓
Enter username: john_doe
Enter password: MyPassword123
Select container: ptvnc3
  ↓
Click [Create User]
  ↓
✓ User created and assigned to ptvnc3
```

**Result:**
- User can login to Guacamole
- User sees only assigned container
- User can access Packet Tracer immediately

---

### Method 3: Bulk Create Button (Multiple Users)

**Best for:** Classroom deployment, creating all students at once

```
Prepare CSV file:
─────────────────
username,password
alice,Pass123!
bob,Pass456!
charlie,Pass789!

Upload CSV → Check "Create New Containers Per User" → Click [Create Users]
  ↓
✓ 3 users created
✓ 3 containers created (ptvnc10, ptvnc11, ptvnc12)
✓ Each user assigned their own container
```

**Result:**
- Each student gets dedicated container
- No shared resources
- Isolated lab environments

---

## Quick Actions

| What do I need? | Button to Click | Location |
|---|---|---|
| Test a new container | Create Instance | Containers card header |
| Add one student | Create User | Users card header |
| Deploy 40 students | Bulk Create | Users card header |
| Delete a user | Delete (row action) | Users table |
| Delete all users from file | Bulk Delete | Users card header |
| Stop a container | Stop (row action) | Containers table |

---

## API Endpoints (For Direct Integration)

### Create Container + Auto-Register
```bash
curl -X POST http://pt-management:5000/api/containers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "ptvnc10",
    "image": "ptvnc"
  }'

# Response
{
  "success": true,
  "container_name": "ptvnc10",
  "connection_name": "pt10",
  "connection_id": 10,
  "message": "Container ptvnc10 created and registered successfully"
}
```

### Create User
```bash
curl -X POST http://pt-management:5000/api/users \
  -H "Content-Type: application/json" \
  -d '{
    "users": [{
      "username": "student05",
      "password": "StudentPass123",
      "container": "ptvnc3"
    }]
  }'

# Response
{
  "success": true,
  "count_created": 1,
  "count_failed": 0,
  "users_created": ["student05"]
}
```

### List All Containers
```bash
curl http://pt-management:5000/api/containers

# Response includes: name, status, image, ports
```

### Get Container Logs
```bash
curl http://pt-management:5000/api/containers/ptvnc3/logs

# Response: Container startup logs
```

---

## Common Scenarios

### Scenario 1: Prepare for Class Tomorrow
```
Monday Morning:
1. Dashboard → Containers → [Create Instance]
2. Create 10 containers: ptvnc10 through ptvnc19
3. All auto-register in Guacamole
4. Done! Ready for class

Tuesday:
1. Prepare students.csv with 30 students
2. Dashboard → Users → [Bulk Create]
3. Upload CSV, check "Create New Containers Per User"
4. Click [Create Users]
5. 30 students created, 30 containers created, all assigned
6. Send login credentials to students
```

### Scenario 2: Add Late Student
```
1. Dashboard → Users → [Create User]
2. Enter student name: michael_chen
3. Enter password: temporary123
4. Select container: ptvnc5 (available container)
5. Click [Create User]
6. Send credentials to michael_chen
```

### Scenario 3: More Students Than Containers
```
Current: 30 students, 10 containers
Need: Share containers

Dashboard → Users → [Bulk Create]
1. Prepare students.csv (20 more students)
2. Upload CSV
3. UNCHECK "Create New Containers Per User"
4. Select container: ptvnc15 (or any shared container)
5. All 20 new students assigned to ptvnc15
```

### Scenario 4: Problem Student Container
```
ptvnc5 has issues, need to reset it

Option A - Delete and recreate:
1. Stop container: Containers → ptvnc5 → [Stop]
2. Delete container: Dashboard → [Actions] → [Delete]
3. Create new: [Create Instance] → Enter ptvnc5 again
4. Users stay assigned, container reset

Option B - Just get logs:
1. Dashboard → Containers → ptvnc5
2. Click [View Logs]
3. Check for errors, restart if needed
```

---

## Troubleshooting

### Container created but not in Guacamole
**Solution:** Use `/api/containers/register` endpoint manually:
```bash
curl -X POST http://pt-management:5000/api/containers/register \
  -H "Content-Type: application/json" \
  -d '{
    "container_name": "ptvnc5",
    "connection_name": "pt05"
  }'
```

### User created but can't see container
**Possible causes:**
1. Container not registered in Guacamole → Use register endpoint
2. User permissions not set → Check guacamole_connection_permission table
3. User-container mapping missing → Check user_container_mapping table

**Fix:**
```sql
-- Check if permission exists
SELECT * FROM guacamole_connection_permission 
WHERE connection_id = 3 AND user_id = 5;

-- If missing, grant permission
INSERT INTO guacamole_connection_permission 
  (connection_id, user_id, permission) 
VALUES (3, 5, 'READ');
```

### Container won't start
**Check logs:**
```bash
docker logs ptvnc5
```

**Common issues:**
- Port already in use
- Not enough disk space
- Memory constraints
- Missing Packet Tracer binary

**Solution:**
```bash
# Check available space
docker exec ptvnc5 df -h

# Check memory usage
docker stats ptvnc5

# Check Packet Tracer installation
docker exec ptvnc5 ls -la /opt/pt/
```

---

## Performance Tips

### For Fast Deployment
1. **Batch create containers first:**
   ```bash
   Create Instance → Create 20 containers
   Takes ~1 minute total
   ```

2. **Then batch create users:**
   ```bash
   Bulk Create → Assign to existing containers
   Takes ~30 seconds
   ```

3. **Why?** Docker image pulls and container boots happen in parallel, much faster than sequential

### Scaling to 100+ Students
```
Recommended approach:
1. Pre-create 100 containers (takes ~5 min)
2. Create users in batches of 50 (takes ~2 min per batch)
3. Total: ~10 minutes for 100 students

Alternative - Dedicated containers per student:
1. Bulk create with "Create New Containers Per User"
2. 100 containers + 100 users created automatically
3. Takes ~10-15 minutes depending on I/O
```

---

## File Formats

### CSV for Bulk Create Users
```
# Required format:
username,password

# Example:
alice,Welcome123!
bob,Welcome456!
charlie,Welcome789!
david,Welcome000!

# Notes:
- First row treated as header if it looks like "username,password"
- Passwords are NOT hidden in preview
- Whitespace trimmed automatically
- Empty lines skipped
```

### CSV for Bulk Delete Users
```
# Format 1 (just username):
student01
student02
student03

# Format 2 (username,password - password ignored):
student01,anypassword
student02,anypassword

# Notes:
- Any line with just a username works
- Password ignored if provided
- Header row ignored
```

---

## Container Auto-Registration Feature

**What happens when you create a container:**

```
POST /api/containers
  ↓
1. Docker container created with:
   - Shared Packet Tracer volume (pt_opt:/opt/pt)
   - Shared files bind mount (/shared)
   - Environment variables
   ↓
2. Container automatically registered in Guacamole:
   - VNC connection entry created
   - Proxy configured (guacd:4822)
   - Max connections limited
   - Connection name generated
   ↓
3. Response returns:
   - Container name
   - Connection ID
   - Connection name
   ↓
4. Container immediately visible in:
   - Guacamole UI
   - pt-management dashboard
   - User assignment dropdowns
```

**Benefits:**
- No manual registration needed
- One-click deployment
- Automatic naming convention
- Immediate availability

---

## Database Tables Involved

```
guacamole_user
  ↓ (1-to-many)
guacamole_connection_permission
  ↓
guacamole_connection (VNC connections)
  ↓
Docker containers (ptvnc1, ptvnc2, ...)
  ↓
user_container_mapping (tracks assignments)
```

---

## Login Credentials

**System Admin:**
- Username: `ptadmin`
- Password: `IlovePT`
- Access: Full pt-management dashboard

**Students:**
- Username: As created in Bulk Create
- Password: As specified in CSV
- Access: Only assigned Guacamole connections

---

## Support Quick Links

- **Dashboard:** http://pt-management:5000
- **Guacamole:** http://guacamole:8080
- **Logs:** `docker logs pt-management`
- **Database:** `docker exec guacamole-mariadb mariadb ...`
- **API Docs:** See API Endpoints section above
