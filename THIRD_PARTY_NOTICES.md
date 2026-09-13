# Spelling dependencies

SammyAI uses unmodified [Spylls 0.1.7](https://pypi.org/project/spylls/0.1.7/),
a pure-Python Hunspell implementation licensed under MPL-2.0.
Source: https://github.com/zverok/spylls.
The MPL notice is included in `sammyai_core/licenses/SPYLLS-MPL-2.0.txt`.

Its wheel bundles the US English SCOWL/Hunspell dictionary, version 2020.12.07,
including both `en_US.aff` and `en_US.dic`. No dictionary download or native
Hunspell installation is needed at runtime. The dictionary has its own SCOWL,
BSD-style and source-component notices; it is not covered solely by Spylls' MPL.
The complete upstream attribution and permission text is reproduced unchanged
in `sammyai_core/licenses/SCOWL-en-US.txt` and included in SammyAI wheels.

The pinned Spylls wheel carries the dictionary data as dependency package data;
SammyAI does not duplicate or modify it. Both dependency manifests include the
same pin. A future frozen executable must collect `spylls.hunspell/data/en/*`
and the license notices; the current supported packaging path is Python wheels.
