import dotenv

env = dotenv.dotenv_values()

SPOTIFY_USER_ID = env.get("SPOTIFY_USER_ID")
