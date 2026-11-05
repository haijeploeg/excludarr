from alembic import context
from sqlalchemy import create_engine

from excludarr.storage.models import Base

url = context.config.get_main_option("sqlalchemy.url")
engine = create_engine(url)
with engine.connect() as conn:
    context.configure(connection=conn, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
