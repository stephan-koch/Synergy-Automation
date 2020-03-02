 
from hpOneView.oneview_client import OneViewClient
from pprint import pprint

config = {
    "api_version": "1200",
    "ip": "10.0.20.50",
    "credentials": {
        "userName": "XXXXX",
        "authLoginDomain": "local",
        "password": "XXXXX"
    }
}
oneview_client = OneViewClient(config)

print ("logged in to OneView")

#server = server_hardwares.get_by_name(server_name)
#server_hardwares = oneview_client.server_hardware

powerOn = {
    "powerState": "On",
    "powerControl": "MomentaryPress"
}

powerOff = {
    "powerState": "Off",
    "powerControl": "PressAndHold"
}

template_name = "ANSIBLE_OS_Deploy_via_iLO"
profile_name = "Roundtable - API Demo Server"


template = oneview_client.server_profile_templates.get_by_name(template_name)

server = oneview_client.server_hardware.get_by_name( "CTC H5 HE11, bay 2")
server_hardware_uri=server.data['uri'] 


basic_profile_options = template.get_new_profile()
#print(basic_profile_options)

basic_profile_options['name'] = profile_name
basic_profile_options['serverHardwareUri'] = server_hardware_uri


#server_template_uri = server_template_data.data['uri']

#print(server_template_uri)


server_power = server.update_power_state(powerOff) # turn off server

print ("create server profile")
try:

    profile = oneview_client.server_profiles.create(basic_profile_options)
    
except:
    print(server_name + " Server already exists")


print("server profile created")

#server_power = server.update_power_state(powerOn) # turn off server
#print ("server powered on .........")


# get the ilo IP and an Token to login to ilo

import re
#server = oneview_client.server_hardware.get_by_name( "CTC H5 HE11, bay 2")
#pprint(server.data['mpHostInfo']['mpIpAddresses'][1]['address'])

remote_console_url = server.get_remote_console_url()
pprint(remote_console_url['remoteConsoleUrl'])

ssoRootUriHostAddressMatchObj = re.search( r'addr=(\d{1,3}.\d{1,3}.\d{1,3}.\d{1,3})', remote_console_url['remoteConsoleUrl'], re.M|re.I)
ssoTokenMatchObj = re.search( r'sessionkey=(\S*)$', remote_console_url['remoteConsoleUrl'], re.M|re.I)  # This will get the session token that you will then use to pass to the iLO RedFish interface


server_address = ssoRootUriHostAddressMatchObj.group(1)
pprint(server_address)
Token = ssoTokenMatchObj.group(1)

pprint(Token)
redFishSsoSessionObject = { "RootUri": server_address, "Token": Token }



print ("mount iso on virtual media")
# with uid + pwd
import sys
import json
from redfish import RedfishClient
from redfish.rest.v1 import ServerDownOrUnreachableError

SYSTEM_URL = ("https://" + server_address)
LOGIN_ACCOUNT = "XXXXX"
LOGIN_PASSWORD = "XXXXX"
MEDIA_URL = "http://osdepl.demo.local/centos/centos7custom.iso"

def get_resource_directory(redfishobj):

    try:
        resource_uri = redfishobj.root.obj.Oem.Hpe.Links.ResourceDirectory['@odata.id']
    except KeyError:
        sys.stderr.write("Resource directory is only available on HPE servers.\n")
        return None

    response = redfishobj.get(resource_uri)
    resources = []

    if response.status == 200:
        sys.stdout.write("\tFound resource directory at /redfish/v1/resourcedirectory" + "\n\n")
        resources = response.dict["Instances"]
    else:
        sys.stderr.write("\tResource directory missing at /redfish/v1/resourcedirectory" + "\n")

    return resources


def mount_virtual_media_iso(_redfishobj, iso_url, media_type, boot_on_next_server_reset):

    virtual_media_uri = None
    virtual_media_response = []

    resource_instances = get_resource_directory(_redfishobj)
    if DISABLE_RESOURCE_DIR or not resource_instances:
        #if we do not have a resource directory or want to force it's non use to find the
        #relevant URI
        managers_uri = _redfishobj.root.obj['Managers']['@odata.id']
        managers_response = _redfishobj.get(managers_uri)
        managers_members_uri = next(iter(managers_response.obj['Members']))['@odata.id']
        managers_members_response = _redfishobj.get(managers_members_uri)
        virtual_media_uri = managers_members_response.obj['VirtualMedia']['@odata.id']
    else:
        for instance in resource_instances:
            #Use Resource directory to find the relevant URI
            if '#VirtualMediaCollection.' in instance['@odata.type']:
                virtual_media_uri = instance['@odata.id']

    if virtual_media_uri:
        virtual_media_response = _redfishobj.get(virtual_media_uri)
        for virtual_media_slot in virtual_media_response.obj['Members']:
            data = _redfishobj.get(virtual_media_slot['@odata.id'])
            if media_type in data.dict['MediaTypes']:
                virtual_media_mount_uri = data.obj['Actions']['#VirtualMedia.InsertMedia']['target']
                post_body = {"Image": iso_url}

                if iso_url:
                    resp = _redfishobj.post(virtual_media_mount_uri, post_body)
                    if boot_on_next_server_reset is not None:
                        patch_body = {}
                        patch_body["Oem"] = {"Hpe": {"BootOnNextServerReset": \
                                                 boot_on_next_server_reset}}
                        boot_resp = _redfishobj.patch(data.obj['@odata.id'], patch_body)
                        if not boot_resp.status == 200:
                            sys.stderr.write("Failure setting BootOnNextServerReset")
                    if resp.status == 400:
                        try:
                            print(json.dumps(resp.obj['error']['@Message.ExtendedInfo'], indent=4, \
                                                                                    sort_keys=True))
                        except Exception as excp:
                            sys.stderr.write("A response error occurred, unable to access iLO"
                                             "Extended Message Info...")
                    elif resp.status != 200:
                        sys.stderr.write("An http response of \'%s\' was returned.\n" % resp.status)
                    else:
                        print("Success!\n")
                        print(json.dumps(resp.dict, indent=4, sort_keys=True))
                break

if __name__ == "__main__":
    

    
    #specify the type of content the media represents
    MEDIA_TYPE = "CD" #current possible options: Floppy, USBStick, CD, DVD
    #specify if the server should attempt to boot this media on system restart
    BOOT_ON_NEXT_SERVER_RESET = True

    # flag to force disable resource directory. Resource directory and associated operations are
    # intended for HPE servers.
    DISABLE_RESOURCE_DIR = False

    try:
        # Create a Redfish client object
        REDFISHOBJ = RedfishClient(base_url=SYSTEM_URL, username=LOGIN_ACCOUNT, \
                                                                            password=LOGIN_PASSWORD)
        # Login with the Redfish client
        REDFISHOBJ.login()
    except ServerDownOrUnreachableError as excp:
        sys.stderr.write("ERROR: server not reachable or does not support RedFish.\n")
        sys.exit()

    mount_virtual_media_iso(REDFISHOBJ, MEDIA_URL, MEDIA_TYPE, BOOT_ON_NEXT_SERVER_RESET)
    REDFISHOBJ.logout()

    
    
print ("create kickstart file")    
OSIP="10.0.33.131"
HOSTNAME="centos01"

#create kickstart File on Webserver Directory
f= open("/persistent/osdepl/centos/centos7ks.cfg","w+")



f.write('lang en_US.UTF-8\n')
f.write('keyboard us\n')
f.write('timezone --utc America/New_York\n')
f.write('text\n')
f.write('install\n')
f.write('skipx\n')
f.write('network  --bootproto=static --ip=%s --netmask=255.255.255.0 ' % OSIP)
f.write(' --gateway=10.0.33.254 --nameserver=10.0.20.5 --hostname=%s\n' %  HOSTNAME)
f.write('authconfig --enable shadow --enablemd5\n')
f.write('firstboot --enable\n')
f.write('cdrom\n')
f.write('rootpw HP1nvent\n')
f.write('ignoredisk --only-use=/dev/disk/by-id/dm-name-mpatha\n')
f.write('zerombr\n')
f.write('clearpart --all --initlabel\n')
f.write('autopart --type=lvm\n')
f.write('reboot\n')
f.write('\n')
f.write('user --name=vagrant --plaintext --password vagrant --groups=vagrant,wheel\n')
f.write('\n')
f.write('#repo --name=docker --baseurl=https://download.docker.com/linux/centos/docker-ce.repo\n')
f.write('\n')
f.write('# Disable firewall and selinux\n')
f.write('firewall --disabled\n')
f.write('selinux --disabled\n')
f.write('\n')
f.write('%pre\n')
f.write('%end\n')
f.write('\n')
f.write('%packages\n')
f.write('@Base\n')
f.write('@Core\n')
f.write('%end\n')
f.write('\n')
f.write('\n')
f.write('%post\n')
f.write('echo "vagrant        ALL=(ALL)       NOPASSWD: ALL" >> /etc/sudoers.d/vagrant\n')
f.write('sed -i "s/^.*requiretty/#Defaults requiretty/" /etc/sudoers\n')
f.write('\n')
f.write('/bin/mkdir /home/vagrant/.ssh\n')
f.write('/bin/chmod 700 /home/vagrant/.ssh\n')
f.write('/bin/chown vagrant:vagrant /home/vagrant/.ssh\n')
f.write('/bin/echo -e "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDKphudM9WIBRid2DKz/UlQ+t99bKMBfmynwy0Fj3ugolElu0lsCr0wRMeopHr5NyUz0EI4diO1CKSwu53axvQr8Lquu8W4/fi39r027efu0xMsCf2eJFY+b7a8wyC8Y+UhXRfFxXWixuLxC06vlrew26Z7UXzk+WRCb/ixiN8wfRryUIROZ4RrV4cUt/gcobMSyvNVKJksHfy/1MAGbwzene6dlHXeSrw7ipc721AqYgvdiGAc5UryDSJZpFTdAMY1aLQUOP7FlUNH30tHOyZLrp9HBhtQ3gZO7rsHJwgtIIw5DnRF8BRmDq5AKvyDZRrEDEHirMTAt+BetokBA6DF skoch@ansible" > /home/vagrant/.ssh/authorized_keys')
f.write('/bin/chown -R vagrant:vagrant /home/vagrant/.ssh\n')
f.write('  \n')
f.write('/usr/bin/yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo\n')
f.write('/usr/bin/yum install docker-ce -y\n')
f.write('/usr/bin/systemctl enable docker\n')
f.write('\n')
f.write('/usr/sbin/usermod  -a -G docker vagrant\n')
f.write('/usr/bin/yum -y install epel-release\n')
f.write('/usr/bin/yum -y install python-pip\n')
f.write('/usr/bin/pip install docker-py\n')
f.write('%end\n')
f.write('\n')

f.close()


#powerOn = {
#    "powerState": "On",
#    "powerControl": "MomentaryPress"
#}



#server = oneview_client.server_hardware.get_by_name( "CTC H5 HE11, bay 1")

## Power on Server and start Installation by booting from virtual media
server_power = server.update_power_state(powerOn) # turn off server
print ("server powered on")



import os
import paramiko
import time

ssh = paramiko.SSHClient()

#server_name = "Roundtable - API Demo Server"
username = 'root'
password = 'HP1nvent'

        
ip_address=OSIP        
print("We are pinging the server: "+ ip_address +" to wait till it´s online..."     )
        
# wait until Server is up .....

waiting=True
counter=0


import socket
def isOpen(ip,port):
   s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
   try:
      s.connect((ip, int(port)))
      s.shutdown(2)
      return True
   except:
      return False


while not isOpen(OSIP,"22"):
        time.sleep(10)
        print("waiting to finish boot ")  
        
time.sleep(20) 
print("starting nginx container")

print("Login with user: " + username + " Server:" + ip_address)        
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())         # add unknown Host-Keys
ssh.connect(ip_address, username=username, password=password)     # login
# ssh.exec_command('systemctl restart docker')                      # workaround for our docker environment

ssh.exec_command('docker run -d --name nginx -p 80:80 nginx')
time.sleep(10)
stdin, stdout, stderr = ssh.exec_command("docker exec -it nginx sed -i '\''s/nginx/Discover More/g'\'' /usr/share/nginx/html/index.html", get_pty=True)
time.sleep(5)
stdin, stdout, stderr = ssh.exec_command("docker exec -it nginx sed -i '\''s/nginx/Discover More/g'\'' /usr/share/nginx/html/index.html", get_pty=True)
print("http://" + ip_address)
# print(stdout.read())
# print(stderr.read())

