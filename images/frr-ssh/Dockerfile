# FRRouting with an SSH server so that Netmiko can reach the routers the same
# way it would reach a physical switch (SSH + CLI). vtysh is the CLI.
# Lab-only credentials: netops / netops.
FROM quay.io/frrouting/frr:10.2.1

RUN apk add --no-cache openssh-server \
 && ssh-keygen -A \
 && adduser -D -s /bin/bash netops \
 && addgroup netops frrvty \
 && addgroup netops frr \
 && echo 'netops:netops' | chpasswd \
 && sed -i -e 's/^#\?PasswordAuthentication.*/PasswordAuthentication yes/' \
           -e 's/^#\?UseDNS.*/UseDNS no/' /etc/ssh/sshd_config \
 && printf 'PermitRootLogin no\nMaxSessions 20\n' >> /etc/ssh/sshd_config \
 && echo 'service integrated-vtysh-config' > /etc/frr/vtysh.conf \
 && chown frr:frr /etc/frr/vtysh.conf

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/sbin/tini", "--", "/usr/local/bin/entrypoint.sh"]
