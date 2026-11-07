from sqlalchemy import create_engine
from sqlalchemy.ext.automap import automap_base

DATABASE_URL = "sqlite:///./incentive-util.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

Base = automap_base()
Base.prepare(autoload_with=engine)
