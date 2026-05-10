import os
import subprocess
import sys

print("Installing requirements...")
subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)

print("Installing Playwright browsers...")
subprocess.run([sys.executable, "-m", "playwright", "install"], check=True)

print("Downloading agency-agent expert personas...")
download_script = os.path.join(os.path.dirname(__file__), "scripts", "download_agents.py")
if os.path.exists(download_script):
    subprocess.run([sys.executable, download_script], check=False)
else:
    print(f"  Warning: {download_script} not found, skipping agent download.")

print("\n✅ Setup complete! Run 'python main.py' to start FRIDAY-MT67.")
