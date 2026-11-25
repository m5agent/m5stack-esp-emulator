import M5
from candidate_lvgl_loop import event_loop
import m5ui.port as m5ui_port


M5.begin()
m5ui_port.event_loop = event_loop
print("M5_UIFLOW_WORKBENCH_READY")
