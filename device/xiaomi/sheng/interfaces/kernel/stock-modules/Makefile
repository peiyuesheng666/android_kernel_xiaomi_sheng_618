# SPDX-License-Identifier: Apache-2.0
.PHONY: all modules modules_install
all modules:
	@test -d "$(CURDIR)/../../../../sheng-kernel/stock-modules"

modules_install:
	python3 $(CURDIR)/stage.py --kernel-out "$(O)" --install-root "$(INSTALL_MOD_PATH)" --stock-dir "$(abspath $(CURDIR)/../../../../sheng-kernel/stock-modules)" --module-plan "$(CURDIR)/module-plan.json"
