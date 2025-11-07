# Fresh Guacamole Database Analysis - November 5, 2025

## Summary

Successfully created a fresh official Guacamole 1.6.0 database from Apache's official schema (not from ptremote project) and verified authentication works correctly.

## Key Finding

**The original ptremote database was indeed altered and had compatibility issues.**

We created a completely fresh database from official Apache Guacamole 1.6.0 sources and:
- ✅ **Default admin login works perfectly**: `guacadmin/guacadmin` → auth token issued successfully
- ✅ **Database structure is correct**: 32-byte password_hash, 32-byte password_salt (binary format)
- ✅ **Official credentials work immediately**: No configuration issues

## Process

### 1. Downloaded Official Guacamole Schema
```bash
wget https://archive.apache.org/dist/guacamole/1.6.0/binary/guacamole-auth-jdbc-1.6.0.tar.gz
tar -xzf guacamole-auth-jdbc-1.6.0.tar.gz
```

### 2. Created Fresh MariaDB Database
- Created clean database: `guacamole_db`
- Imported official schema files:
  - `001-create-schema.sql` - Creates all tables
  - `002-create-admin-user.sql` - Creates default admin user with official hardcoded hash

### 3. Verified Admin User
```sql
SELECT u.user_id, e.name, HEX(u.password_hash) as hash, HEX(u.password_salt) as salt 
FROM guacamole_user u 
JOIN guacamole_entity e ON u.entity_id = e.entity_id;

-- Result:
-- user_id | name      | hash (official hardcoded)
-- 1       | guacadmin | CA458A7D494E3BE824F5E1E175A1556C0F8EEF2C2D7DF3633BEC4A29C4411960
```

### 4. Exported Fresh Database
```bash
mariadb-dump -u guacamole_user -pguacamole_password guacamole_db > fresh-db-dump.sql
```

### 5. Updated Project
- Replaced `ptweb-vnc/db-dump.sql` with fresh official dump
- Deployed fresh infrastructure
- **✅ Test successful**: Admin login returns valid auth token

## Tested Authentication

```bash
curl -k "http://172.17.0.6:8080/guacamole/api/tokens" \
  -d "username=guacadmin&password=guacadmin"

# Result:
{
    "authToken": "3CBA87F95E28491FC4944A688EF01E5C22E362782B775D0B19E7E49A10DAE7EC",
    "username": "guacadmin",
    "dataSource": "mysql",
    "availableDataSources": [
        "mysql",
        "mysql-shared"
    ]
}
```

## Impact

1. **The ptremote project had an altered/incompatible database** - This explains many of the issues
2. **Using official Guacamole schema solves core problems** - Authentication now works from start
3. **Next: Test creating new users** - We can now focus on proper user creation workflow

## Next Steps

1. ✅ Fresh official DB deployed and working
2. ⏳ Create test user through Guacamole UI
3. ⏳ Verify password authentication for UI-created users
4. ⏳ Test if programmatic user creation works with official schema
5. ⏳ E2E test: Create user → Create container → Verify access

## Files Modified

- `ptweb-vnc/db-dump.sql` - Replaced with official Guacamole 1.6.0 dump (clean schema)

## Database Details

- **Schema Version**: Official Apache Guacamole 1.6.0
- **Source**: https://archive.apache.org/dist/guacamole/1.6.0/binary/
- **Database User**: `ptdbuser` (from .env configuration)
- **Database**: `guacamole_db`
- **Default Admin**: `guacadmin` / `guacadmin`
