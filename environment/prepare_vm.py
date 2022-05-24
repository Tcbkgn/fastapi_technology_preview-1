import argparse
import datetime
from itertools import cycle
from ntpath import join
import shutil
from urllib.parse import urljoin
from urllib.request import urlretrieve
from pathlib import Path
import zipfile
import os
import sys
import time
import subprocess

# Default VM configuration
vmname = "FastAPI-1"
cpus = 4
memory = 2048
storage = 8192

domain = "dl.fedoraproject.org"
distro = "fedora"
version = "36"
# https://dl.fedoraproject.org/pub/fedora/linux/releases/36/Everything/x86_64/os/
images_url = f'http://{domain}/pub/{distro}/linux/releases/{version}/Everything/x86_64/os/'
pxe_url = f"{images_url}/images/pxeboot/"
isolinux_url = f"{images_url}/isolinux/"
images_dir = "./images"
isolinux_dir = "./isolinux"
syslinux_url = "https://www.kernel.org/pub/linux/utils/boot/syslinux/"
syslinux_file = "syslinux-6.03.zip"
tftp_dir = "TFTP"

def make_dir(path):
    try:
        path.mkdir(parents=True, exist_ok=True )
        print(f"mkdir: {path}")
    except FileExistsError:
        pass

def download_pxe():
    files = ["initrd.img", "vmlinuz"]
    path = Path(images_dir, "pxeboot")
    make_dir(path)
    for file in files:
        url = urljoin(pxe_url, file)
        print(f"Downloading: {url}")
        urlretrieve(url, path.joinpath(file))

def download_isolinux():
    files = ["ldlinux.c32", "libcom32.c32", "libutil.c32", "vesamenu.c32"]
    path = Path(images_dir, "isolinux")
    make_dir(path)
    for file in files:
        url = urljoin(isolinux_url, file)
        print(f"Downloading: {url}")
        urlretrieve(url, path.joinpath(file))

def download_syslinux():
    url = urljoin(syslinux_url, syslinux_file)
    path = Path(images_dir, "syslinux")
    make_dir(path)
    dst_file = path.joinpath(syslinux_file)
    dst_dir = dst_file.parent
    print(f"Downloading: {url}")
    urlretrieve(url, dst_file)
    with zipfile.ZipFile(dst_file, 'r') as zip_fd:
        zip_fd.extractall(dst_dir)

def get_vbox_path():
    return Path(Path.home().joinpath(".VirtualBox"))

def get_pxelinux_path():
    vbox_path = get_vbox_path()
    return vbox_path.joinpath(tftp_dir)

def create_tftp():
    pxelinux_path = get_pxelinux_path()
    try:
        pxelinux_path.mkdir()
    except FileExistsError:
        pass
    pxe_files = [
        "images/syslinux/bios/com32/lib/libcom32.c32", 
        "images/syslinux/bios/com32/menu/vesamenu.c32",
        "images/syslinux/bios/com32/libutil/libutil.c32",
        "images/syslinux/bios/com32/elflink/ldlinux/ldlinux.c32",
        "images/syslinux/bios/com32/menu/menu.c32",
        "images/syslinux/bios/com32/chain/chain.c32",
        "images/syslinux/bios/core/pxelinux.0"
    ]
    for file in pxe_files:
        src = Path(file)
        dst = Path(pxelinux_path).joinpath(src.name)
        print(f"Copy: src={src} dst={dst}")
        shutil.copyfile(src, dst)

    images_dir = "images"
    distro_dir = Path(images_dir).joinpath(distro).joinpath(version)
    distro_path = pxelinux_path.joinpath(distro_dir)
    try:
        distro_path.mkdir(parents=True, exist_ok=True )
    except FileExistsError:
        pass
    distro_files = [
        "images/pxeboot/initrd.img",
        "images/pxeboot/vmlinuz"
    ]
    for file in distro_files:
        src = Path(file)
        dst = Path(distro_path).joinpath(src.name)
        print(f"Copy: src={src} dst={dst}")
        shutil.copyfile(src, dst)

def update_tftp_config():
    vbox_path = get_vbox_path()
    pxelinux_path = get_pxelinux_path()
    pxelinuxcfg_path = vbox_path.joinpath(pxelinux_path).joinpath("pxelinux.cfg")
    try:
        pxelinuxcfg_path.mkdir()
    except FileExistsError:
        pass
    dst = pxelinuxcfg_path.joinpath("default")
    shutil.copyfile("pxelinux.cfg", dst)

    kickstart_path = vbox_path.joinpath(pxelinux_path).joinpath("kickstart")
    try:
        kickstart_path.mkdir()
    except FileExistsError:
        pass
    files = [
        f"kickstart/{distro}-ks.cfg"
    ]
    for file in files:
        src = Path(file)
        dst = Path(kickstart_path).joinpath(src.name)
        shutil.copyfile(src, dst)


def execute(args):
    exec = []
    exec.extend(args)
    proc = subprocess.Popen(exec, env=os.environ, stdout=subprocess.PIPE)
    return proc.communicate()

def vboxmanage(args=[]):
    exec = ["VBoxManage.exe"]
    exec.extend(args.split())
    return execute(exec)

def is_running(vmname):
    for line in (vboxmanage("list runningvms")[0] or "").splitlines():
        if vmname == line.rsplit(maxsplit=1)[0].decode().strip('\"'):
            return True

def create_vm():
    update_tftp_config()
    vboxmanage(f"createhd --filename {vmname}.vdi --size {storage}")
    vboxmanage(f"createvm --name {vmname} --ostype RedHat_64 --register")
    vboxmanage(f"modifyvm {vmname} --nested-hw-virt on --memory {memory} --vram=12 --acpi on --nic1 nat --cpus {cpus} --audio none")
    vboxmanage(f"modifyvm {vmname} --boot1 net --boot2 disk --boot3 none --boot4 none")
    vboxmanage(f'storagectl {vmname} --name "SATAController" --add sata --controller IntelAHCI --hostiocache on')
    vboxmanage(f'storageattach {vmname} --storagectl "SATAController" --port 0 --device 0 --type hdd --medium {vmname}.vdi')
    vboxmanage(f"modifyvm {vmname} --nattftpfile1 pxelinux.0")
    vboxmanage(f"startvm {vmname}")
    start = time.time()
    count=cycle(range(1,5+1))
    while True:
        now = time.time()
        elapsed = datetime.timedelta(seconds=now-start)
        print(f"\rWaiting for shut down. Elapsed time {elapsed}", end="")
        if next(count) == 5:
            if not is_running(vmname):
                print()
                break
        time.sleep(1)
    time.sleep(5)
    print(f"{vmname} has shut down")
    vboxmanage(f"modifyvm {vmname} --boot1 disk --boot2 dvd --boot3 none --boot4 none")
    #vboxmanage(f"modifyvm {vmname} --nic1 bridget --bridgeadapter1 eth0")
    print(f"{vmname} is ready to run")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action='store_true')
    parser.add_argument("--createvm", action='store_true')
    parser.add_argument("--ps", action='store_true')
    parser.add_argument("--ls", action='store_true')
    parser.add_argument("--clean", action='store_true')
    args = parser.parse_args()
    if args.download:
        download_pxe()
        download_isolinux()
        download_syslinux()
        create_tftp()
        update_tftp_config()
    if args.createvm:
        create_vm()
    if args.ps:
        print((vboxmanage("list runningvms")[0] or b"").decode())
    if args.ls:
        print((vboxmanage("list vms")[0] or b"").decode())
