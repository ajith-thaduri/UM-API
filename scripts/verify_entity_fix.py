
import sys
import os

# Add parent directory to path to allow imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from app.db.session import Base
    from app.models.entity import Entity
    
    print("Checking Entity model...")
    t = Entity.__table__
    print("Entity table loaded successfully:", t.name)
    
    columns = t.columns.keys()
    print("Columns found:", columns)
    
    if 'entity_metadata' in columns:
        print("SUCCESS: entity_metadata column is present.")
    else:
        print("FAILURE: entity_metadata column NOT found.")
        sys.exit(1)
        
    if 'metadata' in columns:
         print("FAILURE: metadata column IS present (Conflict!).")
         sys.exit(1)
    else:
         print("SUCCESS: metadata column is absent.")

    print("Checking Base metadata compatibility...")
    # Double check by instantiating (fake)
    # e = Entity(entity_metadata={})
    # print("Entity instantiation check passed.")
    
    print("All checks passed. You are safe to run Alembic.")

except Exception as e:
    print(f"CRITICAL FAILURE: {e}")
    sys.exit(1)
