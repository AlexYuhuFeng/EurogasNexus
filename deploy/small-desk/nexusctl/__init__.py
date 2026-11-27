"""`nexus`: install, run, back up, update and repair Eurogas Nexus on one PC.

The small-desk operator tool (docs/product/SMALL_DESK_PLAN.md section 3, items 2, 3 and 7).
It runs on the server PC itself, as root, with only the Python standard library (3.10 or
newer, as Ubuntu LTS ships it) and Docker Engine with the Compose plugin. Every decision
(prerequisites, what a backup keeps, whether an update can be undone, what is a secret) is
plain Python in this package so it is tested and does not depend on one operating system;
the Linux-specific glue is the systemd unit text in ``systemd.py`` and the `nexus` wrapper.

Its output is written for a person who does not know Linux or Docker: each line says what is
fine, what is wrong, and what to do.
"""

TOOL_VERSION = "1.0"
