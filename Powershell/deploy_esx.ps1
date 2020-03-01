# Synergy: Deploy SP and install OS via ilo

###LOGIN
Import-Module -name hponeview.500
$username = "XXXXX"
$password = ConvertTo-SecureString "XXXXXX" -AsPlainText -Force
$psCred = New-Object System.Management.Automation.PSCredential -ArgumentList ($username, $password)

Connect-HPOVMgmt -Hostname 10.0.20.50 -AuthLoginDomain local -Credential $psCred

Write-Host "logged on to Composer ....."

#########Vars: ############
$Template=Get-HPOVServerProfileTemplate -Name "ANSIBLE_OS_Deploy_via_iLO"
### Get the first available server based on the template configuration
##$Server = Get-HPOVServer -InputObject $ServerProfileTemplate -NoProfile | Select -First 1
$ServerName = "CTC H5 HE11, bay 1"
$Server=Get-HPOVServer -Name $ServerName
$OSIP = "10.0.33.130"

$HOSTNAME = "esx01"
$OUT="/persistent/osdepl/esx67/ks_custom67.cfg"
$IsoUrl = "http://osdepl.demo.local/esx67/esx67u3custom.iso" 
#################




#Assign SP from SPT
#Power off Server if on
Stop-HPOVServer -Server $Server -Force -Confirm:$false | Wait-HPOVTaskComplete

$params = @{
        AssignmentType        = "Server";
        Description           = "HPE Synergy 480  Server ";
        Name                  = "Roundtable - API Demo Server (Stephan by POSH)";
        Server                = $Server;
        ServerProfileTemplate = $Template;
}

write-host "create Server Profile from template " $Template.name
New-HPOVServerProfile @params | Wait-HPOVTaskComplete


# mount ISO on ilo, set "next boot from", power on server
$ILOIP = $Server.mpHostInfo.mpIpAddresses[1].address
Write-Host "ilo IP of the blade is: "  $ILOIP

#ilo User defined in Server Profile (Template)
$User = "XXXXXX"
$PW = "XXXXXX"


# Creation of the header

$body1 = @{UserName=$User;Password=$PW} | ConvertTo-Json 
$headers = @{} 
$headers["Content-Type"] = "application/json" 
$headers["OData-Version"] = "4.0" 

$URL = "https://$ILOIP/redfish/v1/SessionService/Sessions/"
$response = Invoke-WebRequest $URL -SkipCertificateCheck -ContentType "application/json" -Method 'POST' -Headers $headers -Body $body1
$Token = $response.Headers['X-Auth-Token'] 



$headers["Content-Type"] = "application/json" 
$headers["X-Auth-Token"] = "$Token" 
#$headers

#Eject Media
$URL = "https://$ILOIP/redfish/v1/Managers/1/VirtualMedia/2/Actions/VirtualMedia.EjectMedia/"
$response = Invoke-WebRequest $URL  -SkipCertificateCheck -ContentType "application/json" -Method 'POST' -Headers $headers 
#$response.StatusDescription 

#$body = @{Image= $IsoUrl;"Oem"= @{"Hpe"= @{"BootOnNextServerReset"= $True}}} | ConvertTo-Json 
$body = @{Image= $IsoUrl } | ConvertTo-Json 


#Mount Media
$URL = "https://$ILOIP/redfish/v1/Managers/1/VirtualMedia/2/Actions/VirtualMedia.InsertMedia/"
$response = Invoke-WebRequest $URL  -SkipCertificateCheck -ContentType "application/json" -Method 'POST' -Headers $headers -Body $body

$response.StatusDescription 

# Patch BootOnNextServerReset= $True
$body = @{"Oem"= @{"Hpe"= @{"BootOnNextServerReset"= $True}}} | ConvertTo-Json 
$URL = "https://$ILOIP/redfish/v1/Managers/1/VirtualMedia/2/"
$response = Invoke-WebRequest $URL  -SkipCertificateCheck -ContentType "application/json" -Method 'PATCH' -Headers $headers -Body $body

$response.StatusDescription 
write-host "ISO mounted at virtual media"

#Power on Server
Start-HPOVServer -Server $Server  




write-host "create kickstart file on webserver"
#write ESX kickstart file on Webserver

'' | Out-File  $OUT
'# Sample scripted installation file' | Out-File -Append $OUT
'# Accept the VMware End User License Agreement' | Out-File -Append $OUT
'vmaccepteula' | Out-File -Append $OUT
'# Set the root password for the DCUI and ESXi Shell' | Out-File -Append $OUT
'rootpw HP1nvent!' | Out-File -Append $OUT
'# Install on the first local disk available on machine' | Out-File -Append $OUT
'clearpart --firstdisk --overwritevmfs' | Out-File -Append $OUT
'install --firstdisk=remote --overwritevmfs' | Out-File -Append $OUT
'# Set the network to DHCP on the first network adapater, use the specified hostname and # Create a portgroup for the VMs' | Out-File -Append $OUT
'network --bootproto=static --addvmportgroup=1 --ip=' + $OSIP + ' --netmask=255.255.255.0 --gateway=10.0.33.254 --nameserver=10.0.20.5 --hostname=' + $HOSTNAME + ' --device=vmnic0' | Out-File -Append $OUT
'# reboots the host after the scripted installation is completed' | Out-File -Append $OUT
'reboot' | Out-File -Append $OUT
'' | Out-File -Append $OUT
'%firstboot --interpreter=busybox' | Out-File -Append $OUT
'# Add an extra nic to vSwitch0 (vmnic2)' | Out-File -Append $OUT
'esxcli network vswitch standard uplink add --uplink-name=vmnic1 --vswitch-name=vSwitch0' | Out-File -Append $OUT
'# Assign an IP-Address to the first VMkernel, this will be used for management' | Out-File -Append $OUT
'# esxcli network ip interface ipv4 set --interface-name=vmk0 --type=dhcp' | Out-File -Append $OUT
'# esxcli network vswitch standard portgroup add --portgroup-name=vMotion --vswitch-# name=vSwitch0' | Out-File -Append $OUT
'esxcli network vswitch standard portgroup set --portgroup-name=vMotion' | Out-File -Append $OUT
'esxcli network ip interface add --interface-name=vmk1 --portgroup-name=vMotion' | Out-File -Append $OUT
'# esxcli network ip interface ipv4 set --interface-name=vmk1 --type=dhcp' | Out-File -Append $OUT
'# Enable vMotion on the newly created VMkernel vmk1' | Out-File -Append $OUT
'vim-cmd hostsvc/vmotion/vnic_set vmk1' | Out-File -Append $OUT
'# Add new vSwitch for VM traffic, assign uplinks, create a portgroup and assign a VLAN ID' | Out-File -Append $OUT
'# esxcli network vswitch standard add --vswitch-name=vSwitch1' | Out-File -Append $OUT
'# esxcli network vswitch standard uplink add --uplink-name=vmnic1 --vswitch-name=vSwitch1' | Out-File -Append $OUT
'# esxcli network vswitch standard uplink add --uplink-name=vmnic3 --vswitch-name=vSwitch1' | Out-File -Append $OUT
'# esxcli network vswitch standard portgroup add --portgroup-name=Production --vswitch-name=vSwitch1' | Out-File -Append $OUT
'# esxcli network vswitch standard portgroup set --portgroup-name=Production --vlan-id=10' | Out-File -Append $OUT
'# Set DNS and hostname' | Out-File -Append $OUT
'# esxcli system hostname set --fqdn=esxi5.localdomain' | Out-File -Append $OUT
'esxcli network ip dns search add --domain=demo.local' | Out-File -Append $OUT
'esxcli network ip dns server add --server=10.0.20.5' | Out-File -Append $OUT
'esxcli network ip dns server add --server=10.0.20.6' | Out-File -Append $OUT
'# Set the default PSP for EMC V-MAX to Round Robin as that is our preferred load balancing mechanism' | Out-File -Append $OUT
'# esxcli storage nmp satp set --default-psp VMW_PSP_RR --satp VMW_SATP_SYMM' | Out-File -Append $OUT
'# Enable SSH and the ESXi Shell' | Out-File -Append $OUT
'vim-cmd hostsvc/enable_ssh' | Out-File -Append $OUT
'vim-cmd hostsvc/start_ssh' | Out-File -Append $OUT
'vim-cmd hostsvc/enable_esx_shell' | Out-File -Append $OUT
'vim-cmd hostsvc/start_esx_shell' | Out-File -Append $OUT

##  install-module VMware.PowerCLI  needed !

do {
  $ping = Test-Connection -TargetName $OSIP  -TcpPort 22
  write-host "waiting sshd on host to come up ..."
  sleep 5
} until ($ping)

write-host "installation finished ..."
# join vcenter

$myvcenter = Connect-VIServer -Server suo04ctcvcsa001.demo.local -Protocol https -User XXXXXX -Password XXXXXX -Force
Add-VMHost -Server "suo04ctcvcsa001.demo.local" -Name $OSIP -Location Democluster -User root -Password HP1nvent! -Force
