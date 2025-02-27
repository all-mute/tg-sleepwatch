import subprocess
import sys

def install_dependencies():
    print("Устанавливаем необходимые зависимости...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "python-telegram-bot[job-queue]", "--upgrade"])
    subprocess.check_call([sys.executable, "-m", "pip", "install", "APScheduler>=3.6.3", "--upgrade"])
    print("Зависимости установлены успешно!")

if __name__ == "__main__":
    install_dependencies() 