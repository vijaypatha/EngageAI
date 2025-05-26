# import os
# import sys
# # Add project root to Python path to find 'app' module
# # This assumes 'alembic' folder is directly inside 'backend', and 'app' is also in 'backend'
# sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), '..')))

# from app.database import Base  # Make sure this path is correct
# from app.models import * # Or import specific model classes

# # +++ INSERT DEBUG LINES HERE +++
# print("DEBUG: alembic/env.py - Project root added to sys.path:")
# print(sys.path[0])
# print("DEBUG: alembic/env.py - Tables known to Base.metadata BEFORE assignment to target_metadata:")
# print(list(Base.metadata.tables.keys()))
# # +++ END OF DEBUG LINES +++

# from logging.config import fileConfig

# from sqlalchemy import engine_from_config
# from sqlalchemy import pool

# from alembic import context

# # this is the Alembic Config object, which provides
# # access to the values within the .ini file in use.
# config = context.config

# # Interpret the config file for Python logging.
# # This line sets up loggers basically.
# if config.config_file_name is not None:
#     fileConfig(config.config_file_name)

# # add your model's MetaData object here
# # for 'autogenerate' support
# # from myapp import mymodel
# # target_metadata = mymodel.Base.metadata
# target_metadata = Base.metadata

# # other values from the config, defined by the needs of env.py,
# # can be acquired:
# # my_important_option = config.get_main_option("my_important_option")
# # ... etc.

# # +++ YOU CAN ADD ANOTHER PRINT HERE TO BE SURE +++
# print("DEBUG: alembic/env.py - Tables in target_metadata AFTER assignment:")
# if target_metadata is not None:
#     print(list(target_metadata.tables.keys()))
# else:
#     print("target_metadata is None")
# # +++ END OF DEBUG LINES +++


# def run_migrations_offline() -> None:
#     """Run migrations in 'offline' mode.

#     This configures the context with just a URL
#     and not an Engine, though an Engine is acceptable
#     here as well.  By skipping the Engine creation
#     we don't even need a DBAPI to be available.

#     Calls to context.execute() here emit the given string to the
#     script output.

#     """
#     url = config.get_main_option("sqlalchemy.url")
#     context.configure(
#         url=url,
#         target_metadata=target_metadata,
#         literal_binds=True,
#         dialect_opts={"paramstyle": "named"},
#     )

#     with context.begin_transaction():
#         context.run_migrations()


# def run_migrations_online() -> None:
#     """Run migrations in 'online' mode.

#     In this scenario we need to create an Engine
#     and associate a connection with the context.

#     """
#     connectable = engine_from_config(
#         config.get_section(config.config_ini_section, {}),
#         prefix="sqlalchemy.",
#         poolclass=pool.NullPool,
#     )

#     with connectable.connect() as connection:
#         context.configure(
#             connection=connection, target_metadata=target_metadata
#         )

#         with context.begin_transaction():
#             context.run_migrations()


# if context.is_offline_mode():
#     run_migrations_offline()
# else:
#     run_migrations_online()


##### TEMP VERISION 

# backend/alembic/env.py

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context

# --- Add project root to Python path ---
# This assumes 'alembic' folder is directly inside 'backend',
# and 'app' (containing models.py and database.py) is also in 'backend'.
PROJECT_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

# --- Import Base and Models ---
# Import Base from your database setup
from app.database import Base

# Import your models module to ensure all model classes are registered with Base.
# This line will execute your app/models.py file.
import app.models

# --- Alembic Config object ---
config = context.config

# --- Configure Python logging ---
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- Debug Prints: Check what models Alembic sees ---
print(f"DEBUG: alembic/env.py - Project root added to sys.path: {PROJECT_ROOT}")
print("DEBUG: alembic/env.py - Tables known to app.database.Base.metadata:")
if Base.metadata:
    print(list(Base.metadata.tables.keys()))
else:
    print("app.database.Base.metadata is None or not yet populated.")

# --- Set target_metadata for Alembic ---
# This is your SQLAlchemy MetaData object that contains your table definitions.
target_metadata = Base.metadata

print("DEBUG: alembic/env.py - Tables in Alembic's target_metadata:")
if target_metadata:
    print(list(target_metadata.tables.keys()))
else:
    print("Alembic's target_metadata is None.")

# --- Alembic migration functions ---
def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.
    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well. By skipping the Engine creation
    we don't even need a DBAPI to be available.
    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True, # Recommended for PostgreSQL to detect type changes
        compare_server_default=True, # Recommended to detect server default changes
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.
    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True, # Recommended for PostgreSQL
            compare_server_default=True, # Recommended
            # Consider include_schemas=True if you use multiple schemas,
            # and version_table_schema if your alembic_version table is in a specific schema.
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

