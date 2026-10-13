#!/bin/bash
# Start sshd in the background, then hand over to the stock FRR start script
# (watchfrr supervising the daemons enabled in /etc/frr/daemons).
/usr/sbin/sshd -E /var/log/sshd.log
exec /usr/lib/frr/docker-start
