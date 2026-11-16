# KubeArmor proof

```
Node 1 : 
 	OS Image:                 	Ubuntu 24.04.5 LTS     	
 	Kernel Version:           	7.0.0-1014-aws         	
 	Kubelet Version:          	v1.37.2+k3s1           	
 	Container Runtime:        	containerd://2.3.7-k3s1	
 	Active LSM:               	AppArmor               	
 	Host Security:            	false                  	
 	Container Security:       	true                   	
 	Container Default Posture:	audit(File)            	audit(Capabilities)	audit(Network)	
 	Host Default Posture:     	audit(File)            	audit(Capabilities)	audit(Network)	
 	Host Visibility:          	none                   	
Armored Up pods : 
+-----------+--------------------------------+------------+--------------------------+---------------------------+
| NAMESPACE |        DEFAULT POSTURE         | VISIBILITY |           NAME           |          POLICY           |
+-----------+--------------------------------+------------+--------------------------+---------------------------+
| wisecow   | File(block),                   | none       | wisecow-77757f9448-62mj2 | wisecow-block-sensitive   |
|           | Capabilities(audit), Network   |            |                          | wisecow-process-allowlist |
|           | (audit)                        |            |                          |                           |
+           +                                +            +--------------------------+---------------------------+
|           |                                |            | wisecow-77757f9448-nkdzp | wisecow-block-sensitive   |
|           |                                |            |                          | wisecow-process-allowlist |
|           |                                |            |                          |                           |
+-----------+--------------------------------+------------+--------------------------+---------------------------+
```

## Before policies (pod wisecow-598985dfc5-bmq8b)

| Attempt | Command | Exit code | Output |
|---|---|---|---|
| list files with ls (not on the allowlist) | `ls /` | 0 | app bin boot dev etc home lib lib64 media mnt opt proc root run sbin srv sys tmp usr var |
| start another shell, sh (not on the allowlist) | `sh -c id` | 0 | uid=10001(wisecow) gid=10001(wisecow) groups=10001(wisecow) |
| run apt-get (not on the allowlist) | `apt-get --version` | 0 | apt 2.6.2 (amd64) Supported modules: *Ver: Standard .deb *Pkg:  Debian dpkg interface (Priority 30)  Pkg:  Debian APT solver interface (Priority -1000)  Pkg:  D |
| read /etc/shadow (blocked file) | `cat /etc/shadow` | 1 | cat: /etc/shadow: Permission denied command terminated with exit code 1 |
| read /etc/hostname (allowed file) | `cat /etc/hostname` | 0 | wisecow-598985dfc5-bmq8b |
| run fortune (on the allowlist) | `/usr/games/fortune -s` | 0 | Next Friday will not be your lucky day.  As a matter of fact, you don't have a lucky day this year. |

App check before policies: wisecow still serves cows

## After policies (pod wisecow-77757f9448-62mj2)

| Attempt | Command | Exit code | Output |
|---|---|---|---|
| list files with ls (not on the allowlist) | `ls /` | 126 | bash: line 1: /usr/bin/ls: Permission denied command terminated with exit code 126 |
| start another shell, sh (not on the allowlist) | `sh -c id` | 126 | bash: line 1: /usr/bin/sh: Permission denied command terminated with exit code 126 |
| run apt-get (not on the allowlist) | `apt-get --version` | 126 | bash: line 1: /usr/bin/apt-get: Permission denied command terminated with exit code 126 |
| read /etc/shadow (blocked file) | `cat /etc/shadow` | 1 | cat: /etc/shadow: Permission denied command terminated with exit code 1 |
| read /etc/hostname (allowed file) | `cat /etc/hostname` | 0 | wisecow-77757f9448-62mj2 |
| run fortune (on the allowlist) | `/usr/games/fortune -s` | 0 | Work consists of whatever a body is obliged to do. Play consists of whatever a body is not obliged to do. 		-- Mark Twain |

App check after policies: wisecow still serves cows

## KubeArmor alerts (count, action, policy, operation, source, resource, result)

```
      1 Block	DefaultPosture	Process	/var/lib/rancher/k3s/data/342d21a06834327c49d125902586b5c58038e4decca01ba829aa819ce4d1b586/bin/runc	/usr/bin/apt-get --version	Permission denied
      1 Block	DefaultPosture	Process	/var/lib/rancher/k3s/data/342d21a06834327c49d125902586b5c58038e4decca01ba829aa819ce4d1b586/bin/runc	/usr/bin/ls /	Permission denied
      1 Block	DefaultPosture	Process	/var/lib/rancher/k3s/data/342d21a06834327c49d125902586b5c58038e4decca01ba829aa819ce4d1b586/bin/runc	/usr/bin/sh -c id	Permission denied
      1 Block	wisecow-block-sensitive	File	/usr/bin/cat /etc/shadow	/usr/lib/x86_64-linux-gnu/libc.so.6	Permission denied
```

Block alerts seen: 4
