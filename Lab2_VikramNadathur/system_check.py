import platform
import subprocess
import json


def gather_system_info():
    system_info = {
        "os": platform.system(),
        "os_version": platform.version(),
        "architecture": platform.architecture(),
        "machine": platform.machine(),
    }

    if system_info["os"] == "Linux":
        system_info["cpu_info"] = subprocess.check_output("lscpu", shell=True).decode()
        system_info["memory_info"] = subprocess.check_output("free -h", shell=True).decode()
        system_info["disk_info"] = subprocess.check_output("df -h", shell=True).decode()

    elif system_info["os"] == "Windows":
        system_info["cpu_info"] = subprocess.check_output(
            "wmic cpu get caption, deviceid, name, numberofcores, maxclockspeed, status",
            shell=True
        ).decode()
        system_info["memory_info"] = subprocess.check_output(
            "wmic memorychip get capacity, speed",
            shell=True
        ).decode()
        system_info["disk_info"] = subprocess.check_output(
            "wmic logicaldisk get size,freespace,caption",
            shell=True
        ).decode()
        system_info["system_info"] = subprocess.check_output(
            "systeminfo",
            shell=True
        ).decode()

    elif system_info["os"] == "Darwin":  # macOS
        system_info["cpu_info"] = subprocess.check_output(
            "sysctl -n machdep.cpu.brand_string", shell=True
        ).decode()
        system_info["memory_info"] = subprocess.check_output(
            "vm_stat", shell=True
        ).decode()
        system_info["disk_info"] = subprocess.check_output(
            "df -h", shell=True
        ).decode()

    return system_info


def save_system_info(info):
    with open("system_info.json", "w") as f:
        json.dump(info, f, indent=4)


if __name__ == "__main__":
    system_info = gather_system_info()
    save_system_info(system_info)
    print("System information saved to system_info.json")
