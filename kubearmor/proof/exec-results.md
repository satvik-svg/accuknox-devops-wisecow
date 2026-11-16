## Before policies (pod wisecow-598985dfc5-ch855)

| Attempt | Command | Exit code | Output |
|---|---|---|---|
| list files with ls (not on the allowlist) | `ls /` | 0 | app bin boot dev etc home lib lib64 media mnt opt proc root run sbin srv sys tmp usr var |
| start another shell, sh (not on the allowlist) | `sh -c id` | 0 | uid=10001(wisecow) gid=10001(wisecow) groups=10001(wisecow) |
| run apt-get (not on the allowlist) | `apt-get --version` | 0 | apt 2.6.2 (amd64) Supported modules: *Ver: Standard .deb *Pkg:  Debian dpkg interface (Priority 30)  Pkg:  Debian APT solver interface (Priority -1000)  Pkg:  D |
| read /etc/shadow (blocked file) | `cat /etc/shadow` | 1 | cat: /etc/shadow: Permission denied command terminated with exit code 1 |
| read /etc/hostname (allowed file) | `cat /etc/hostname` | 0 | wisecow-598985dfc5-ch855 |
| run fortune (on the allowlist) | `/usr/games/fortune -s` | 0 | You are scrupulously honest, frank, and straightforward.  Therefore you have few friends. |

App check before policies: wisecow still serves cows

## After policies (pod wisecow-7d7755495b-pmz7s)

| Attempt | Command | Exit code | Output |
|---|---|---|---|
| list files with ls (not on the allowlist) | `ls /` | 126 | bash: line 1: /usr/bin/ls: Permission denied command terminated with exit code 126 |
| start another shell, sh (not on the allowlist) | `sh -c id` | 126 | bash: line 1: /usr/bin/sh: Permission denied command terminated with exit code 126 |
| run apt-get (not on the allowlist) | `apt-get --version` | 126 | bash: line 1: /usr/bin/apt-get: Permission denied command terminated with exit code 126 |
| read /etc/shadow (blocked file) | `cat /etc/shadow` | 1 | cat: /etc/shadow: Permission denied command terminated with exit code 1 |
| read /etc/hostname (allowed file) | `cat /etc/hostname` | 0 | wisecow-7d7755495b-pmz7s |
| run fortune (on the allowlist) | `/usr/games/fortune -s` | 0 | Q:	Know what the difference between your latest project 	and putting wings on an elephant is? A:	Who knows?  The elephant *might* fly, heh, heh... |

App check after policies: wisecow still serves cows

