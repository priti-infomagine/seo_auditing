# from dotenv import load_dotenv
# from pathlib import Path
# import os

# env_path = Path(__file__).resolve().parent / ".env"
# load_dotenv(env_path, override=True)

# login = os.getenv("DATAFORSEO_LOGIN")
# password = os.getenv("DATAFORSEO_PASSWORD")

# print("Loaded .env:", env_path.exists())
# print("Login:", repr(login))
# print("Password exists:", bool(password))
# # print("Password length:", len(password or ""))


# import os
# from pathlib import Path

# import httpx
# from dotenv import load_dotenv

# load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

# login = os.environ["DATAFORSEO_LOGIN"].strip()
# password = os.environ["DATAFORSEO_PASSWORD"].strip()

# response = httpx.get(
#     "https://api.dataforseo.com/v3/appendix/errors",
#     auth=httpx.BasicAuth(login, password),
#     timeout=20,
# )

# print("HTTP status:", response.status_code)
# print("Response:", response.text)




import os
import base64
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

login = os.environ["DATAFORSEO_LOGIN"].strip()
password = os.environ["DATAFORSEO_PASSWORD"].strip()

generated = base64.b64encode(
    f"{login}:{password}".encode("utf-8")
).decode("ascii")

print("Generated credential length:", len(generated))
print("Login matches expected account:", login == "sunil.gadri@infomagine.in")
print("Password has leading/trailing whitespace:",
      password != password.strip())