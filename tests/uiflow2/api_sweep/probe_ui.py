#!/usr/bin/env python3
"""Generate separate UIFlow2 UI programs for Device Service /program.

No emulator is launched here. Runtime-only methods without an explicit behavior
oracle stay NOT_RUN. Getter checks and pending framebuffer/event checks are
reported separately so merely executing a method cannot become functional PASS.
"""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import re
import struct
import zlib


M5UI_CONSTRUCTORS = {
    "M5Arc": "m5ui.M5Arc(x=80,y=48,w=150,h=150,value=25,parent=page)",
    "M5Bar": "m5ui.M5Bar(x=32,y=90,w=250,h=28,value=25,parent=page)",
    "M5Button": "m5ui.M5Button(text='Touch to count',x=40,y=80,w=240,h=64,parent=page)",
    "M5ButtonMatrix": r"m5ui.M5ButtonMatrix(['A','B','\n','C','D',''],x=20,y=48,w=280,h=150,parent=page)",
    "M5Calendar": "m5ui.M5Calendar(x=45,y=32,w=230,h=200,today_date=[2026,10,27],show_month=[2026,10],parent=page)",
    "M5Canvas": "m5ui.M5Canvas(x=20,y=48,w=280,h=150,bg_c=0x182128,parent=page)",
    "M5Chart": "m5ui.M5Chart(x=44,y=48,w=230,h=140,point_num=5,hdiv=2,vdiv=2,parent=page)",
    "M5Checkbox": "m5ui.M5Checkbox(title='Enable probe',x=40,y=85,title_c=0xF3F7F8,parent=page)",
    "M5Dropdown": "m5ui.M5Dropdown(x=40,y=72,w=240,options=['Alpha','Beta','Gamma'],parent=page)",
    "M5Image": "m5ui.M5Image(__import__('os').getcwd()+'/fixture.png',x=100,y=72,parent=page)",
    "M5Keyboard": "m5ui.M5Keyboard(x=8,y=76,w=304,h=146,target_textarea=textarea,parent=page)",
    "M5Label": "m5ui.M5Label('UIFlow2 label',x=28,y=80,text_c=0xF3F7F8,parent=page)",
    "M5LED": "m5ui.M5LED(x=130,y=88,size=50,color=0x38B8C8,parent=page)",
    "M5Line": "m5ui.M5Line(points=[20,60,100,150,180,60,280,140],width=4,color=0x38B8C8,parent=page)",
    "M5List": "m5ui.M5List(x=20,y=48,w=280,h=150,parent=page)",
    "M5Menu": "m5ui.M5Menu(x=20,y=48,w=280,h=150,page_name='Probe',parent=page)",
    "M5Msgbox": "m5ui.M5Msgbox(title='Probe message',x=20,y=48,w=280,h=150,parent=page)",
    "M5Page": "page",
    "M5Roller": "m5ui.M5Roller(x=40,y=60,w=240,h=130,options=['Alpha','Beta','Gamma'],parent=page)",
    "M5Scale": "m5ui.M5Scale(x=40,y=88,w=240,h=60,parent=page)",
    "M5Slider": "m5ui.M5Slider(x=40,y=100,w=240,h=28,value=25,parent=page)",
    "M5Spinbox": "m5ui.M5Spinbox(x=40,y=84,w=240,h=60,value=25,parent=page)",
    "M5Spinner": "m5ui.M5Spinner(x=105,y=62,w=110,h=110,anim_t=1000,parent=page)",
    "M5Switch": "m5ui.M5Switch(x=110,y=84,w=100,h=50,parent=page)",
    "M5Table": "m5ui.M5Table(x=20,y=48,w=280,h=150,row_cnt=2,col_cnt=2,parent=page)",
    "M5TabView": "m5ui.M5TabView(x=8,y=36,w=304,h=190,bar_size=40,parent=page)",
    "M5TextArea": "m5ui.M5TextArea(text='Probe',placeholder='Type here',x=20,y=60,w=280,h=130,parent=page)",
    "M5Win": "m5ui.M5Win(x=8,y=36,w=304,h=190,parent=page)",
}


# Each entry is (action, expected-state assertion). None means framebuffer or
# real injected input still has to prove the effect outside the guest.
COMMON = {
    "set_flag": ("obj.set_flag(lv.obj.FLAG.HIDDEN,True)", "obj.has_flag(lv.obj.FLAG.HIDDEN)"),
    "toggle_flag": ("obj.remove_flag(lv.obj.FLAG.HIDDEN);obj.toggle_flag(lv.obj.FLAG.HIDDEN)", "obj.has_flag(lv.obj.FLAG.HIDDEN)"),
    "set_state": ("obj.set_state(lv.STATE.DISABLED,True)", "obj.has_state(lv.STATE.DISABLED)"),
    "toggle_state": ("obj.remove_state(lv.STATE.DISABLED);obj.toggle_state(lv.STATE.DISABLED)", "obj.has_state(lv.STATE.DISABLED)"),
    "set_pos": ("obj.set_pos(24,56);obj.update_layout()", "obj.get_x()==24 and obj.get_y()==56"),
    "set_x": ("obj.set_x(28);obj.update_layout()", "obj.get_x()==28"),
    "set_y": ("obj.set_y(64);obj.update_layout()", "obj.get_y()==64"),
    "set_size": ("obj.set_size(160,64);obj.update_layout()", "obj.get_width()==160 and obj.get_height()==64"),
    "set_width": ("obj.set_width(180);obj.update_layout()", "obj.get_width()==180"),
    "set_height": ("obj.set_height(70);obj.update_layout()", "obj.get_height()==70"),
    "get_width": ("obj.set_width(180);obj.update_layout()", "obj.get_width()==180"),
    "get_height": ("obj.set_height(70);obj.update_layout()", "obj.get_height()==70"),
    "align_to": ("obj.align_to(page,lv.ALIGN.CENTER,0,0);obj.update_layout()", None),
    "set_style_radius": ("obj.set_style_radius(6,lv.PART.MAIN)", "obj.get_style_radius(lv.PART.MAIN)==6"),
    "set_style_text_font": ("obj.set_style_text_font(lv.font_montserrat_18,lv.PART.MAIN)", None),
    "set_text_color": ("obj.set_text_color(0x38B8C8,255,lv.PART.MAIN)", "obj.get_style_text_color(lv.PART.MAIN).to_int()==0x38B8C8"),
    "set_bg_color": ("obj.set_bg_color(0x304850,255,lv.PART.MAIN)", "obj.get_style_bg_color(lv.PART.MAIN).to_int()==0x304850"),
    "set_border_color": ("obj.set_border_color(0x38B8C8,255,lv.PART.MAIN)", "obj.get_style_border_color(lv.PART.MAIN).to_int()==0x38B8C8"),
    "set_line_color": ("obj.set_line_color(0x38B8C8,255,lv.PART.MAIN)", "obj.get_style_line_color(lv.PART.MAIN).to_int()==0x38B8C8"),
    "set_bg_grad_color": ("obj.set_bg_grad_color(0x182128,255,0x38B8C8,255,lv.GRAD_DIR.VER,lv.PART.MAIN)", "obj.get_style_bg_grad_color(lv.PART.MAIN).to_int()==0x38B8C8"),
    "get_display_size": ("result=obj.get_display_size()", "tuple(result)==(320,240)"),
    "add_event_cb": ("obj.add_event_cb(on_event,lv.EVENT.ALL,None)", None),
}


SPECIFIC = {
    "M5Arc": {
        "set_arc_color": ("obj.set_arc_color(0x38B8C8,255,lv.PART.INDICATOR)", "obj.get_style_arc_color(lv.PART.INDICATOR).to_int()==0x38B8C8"),
        "set_range": ("obj.set_range(10,90)", "obj.get_min_value()==10 and obj.get_max_value()==90"),
        "set_value": ("obj.set_value(60)", "obj.get_value()==60"),
    },
    "M5Bar": {
        "set_range": ("obj.set_range(10,90)", "obj.get_min_value()==10 and obj.get_max_value()==90"),
        "set_value": ("obj.set_value(60,False)", "obj.get_value()==60"),
    },
    "M5Button": {
        "set_btn_text": ("obj.set_btn_text('Updated button')", "obj.get_btn_text()=='Updated button'"),
        "get_btn_text": ("obj.set_btn_text('Getter check')", "obj.get_btn_text()=='Getter check'"),
        "set_shadow": ("obj.set_shadow(0x38B8C8,255,lv.ALIGN.CENTER,0,0)", None),
        "unset_shadow": ("obj.unset_shadow()", "expected_not_implemented"),
        "set_pressed_effect": ("obj.set_pressed_effect(obj.EFFECT_SIMPLE)", None),
    },
    "M5ButtonMatrix": {
        "toggle_button_ctrl": ("obj.toggle_button_ctrl(0,lv.buttonmatrix.CTRL.CHECKABLE)", "obj.has_button_ctrl(0,lv.buttonmatrix.CTRL.CHECKABLE)"),
        "set_textarea": ("obj.set_textarea(textarea)", "obj.get_textarea()==textarea"),
        "get_textarea": ("obj.set_textarea(textarea)", "obj.get_textarea()==textarea"),
        "get_selected_button": ("obj.set_selected_button(1)", "obj.get_selected_button()==1"),
        "value_changed_event": ("textarea.set_text('');obj.set_textarea(textarea);obj.add_event_cb(on_event,lv.EVENT.VALUE_CHANGED,None)", None),
    },
    "M5Calendar": {
        "set_calendar_style": ("obj.set_calendar_style('dropdown')", None),
        "set_highlighted_dates": ("obj.set_highlighted_dates([2026,10,27,2026,10,28])", "obj.get_highlighted_dates_num()==2"),
    },
    "M5Canvas": {
        "begin_draw": ("obj.begin_draw();obj.draw_rect(4,4,40,40,bg_c=0x38B8C8);obj.end_draw()", "obj.get_px_color(10,10)==0x38B8C8"),
        "end_draw": ("obj.begin_draw();obj.draw_rect(4,4,40,40,bg_c=0x38B8C8);obj.end_draw()", "obj.get_px_color(10,10)==0x38B8C8"),
        "fill_bg": ("obj.fill_bg(0x38B8C8,255)", "obj.get_px_color(10,10)==0x38B8C8"),
        "set_px": ("obj.set_px(20,20,0x38B8C8,255)", "obj.get_px_color(20,20)==0x38B8C8 and obj.get_px_opa(20,20)==255"),
        "get_px_color": ("obj.set_px(20,20,0x38B8C8,255)", "obj.get_px_color(20,20)==0x38B8C8"),
        "get_px_opa": ("obj.set_px(20,20,0x38B8C8,200)", "obj.get_px_opa(20,20)==200"),
        "draw_arc": ("obj.draw_arc(120,70,40,0x38B8C8,255,6,0,180)", None),
        "draw_rect": ("obj.draw_rect(12,12,80,60,bg_c=0x38B8C8)", "obj.get_px_color(40,40)==0x38B8C8"),
        "draw_image": ("obj.draw_image(__import__('os').getcwd()+'/fixture.png',20,20)", None),
        "draw_line": ("obj.draw_line(10,20,230,20,0x38B8C8,255,4)", "obj.get_px_color(100,20)==0x38B8C8"),
        "draw_label": ("obj.draw_label('Canvas text',12,12,color=0xF3F7F8)", None),
        "draw_triangle": ("obj.draw_triangle(20,100,120,10,220,100,bg_c=0x38B8C8)", "obj.get_px_color(120,60)==0x38B8C8"),
    },
    "M5Chart": {
        "x_axis_init": ("obj.x_axis_init()", "obj.x_axis.get_range_min_value()==0 and obj.x_axis.get_range_max_value()==100"),
        "y_axis1_init": ("obj.y_axis1_init()", "obj.y_axis1.get_range_min_value()==0 and obj.y_axis1.get_range_max_value()==100"),
        "y_axis2_init": ("obj.y_axis2_init()", "obj.y_axis2.get_range_min_value()==0 and obj.y_axis2.get_range_max_value()==100"),
        "set_axis_range": ("obj.y_axis1_init();obj.set_axis_range(lv.chart.AXIS.PRIMARY_Y,10,80)", "obj.y_axis1.get_range_min_value()==10 and obj.y_axis1.get_range_max_value()==80"),
        "add_series": ("series=obj.add_series(0x38B8C8,lv.chart.AXIS.PRIMARY_Y);obj.set_series_values(series,[10,40,20,80,60])", "obj.get_series_color(series)==0x38B8C8"),
        "set_series_color": ("series=obj.add_series(0xFFFFFF,lv.chart.AXIS.PRIMARY_Y);obj.set_series_color(series,0x38B8C8)", "obj.get_series_color(series)==0x38B8C8"),
        "get_series_color": ("series=obj.add_series(0x38B8C8,lv.chart.AXIS.PRIMARY_Y)", "obj.get_series_color(series)==0x38B8C8"),
        "set_series_values": ("series=obj.add_series(0x38B8C8,lv.chart.AXIS.PRIMARY_Y);obj.set_series_values(series,[10,40,20,80,60])", None),
    },
    "M5Dropdown": {
        "set_options": ("obj.set_options(['One','Two','Three'])", "obj.get_options()==['One','Two','Three']"),
        "get_options": ("obj.set_options(['One','Two'])", "obj.get_options()==['One','Two']"),
        "add_option": ("obj.add_option('Delta',1)", "obj.get_options()[1]=='Delta'"),
        "clear_options": ("obj.clear_options()", "obj.get_options()==[]"),
        "get_selected_str": ("obj.set_selected(1,False)", "obj.get_selected_str()=='Beta'"),
        "set_dir": ("obj.set_dir(lv.DIR.BOTTOM)", "obj.get_dir()==lv.DIR.BOTTOM"),
    },
    "M5Image": {
        "set_image": ("obj.set_image(__import__('os').getcwd()+'/fixture-alt.png')", None),
        "set_rotation": ("obj.set_rotation(90)", "obj.get_rotation()==900"),
        "set_scale": ("obj.set_scale(1.5)", "obj.get_scale_x()==384 and obj.get_scale_y()==384"),
    },
    "M5Label": {
        "set_shadow": ("obj.set_shadow(0x38B8C8,255,lv.ALIGN.CENTER,0,0)", None),
        "unset_shadow": ("obj.set_shadow(0x38B8C8,255,lv.ALIGN.CENTER,0,0);obj.unset_shadow()", None),
        "set_text": ("obj.set_text('Updated label')", "obj.get_text()=='Updated label'"),
    },
    "M5LED": {
        "set_color": ("obj.set_color(0x38B8C8)", None),
        "set_brightness": ("obj.set_brightness(50)", "obj.get_brightness()==50"),
        "get_brightness": ("obj.set_brightness(60)", "obj.get_brightness()==60"),
    },
    "M5Line": {
        "set_points": ("obj.set_points([20,60,120,100,220,60])", "len(obj.lv_points)==3 and obj.lv_points[1]['y']==100"),
        "add_point": ("obj.add_point(300,80)", "len(obj.lv_points)==5 and obj.lv_points[-1]['x']==300"),
    },
    "M5List": {
        "add_text": ("child=obj.add_text('List section')", "obj.get_child_count()>0"),
        "add_button": ("child=obj.add_button(None,'List button')", "obj.get_child_count()>0"),
    },
    "M5Menu": {
        "add_label": ("child=obj.add_label('Menu item')", None),
        "add_switch": ("child=obj.add_switch('Menu switch')", None),
    },
    "M5Msgbox": {
        "add_text": ("child=obj.add_text('Message body')", None),
        "add_button": ("child=obj.add_button(text='Confirm')", None),
    },
    "M5Page": {"screen_load": ("obj.screen_load()", "lv.screen_active()==obj")},
    "M5Roller": {
        "set_options": ("obj.set_options(['One','Two','Three'])", "obj.get_options()==['One','Two','Three']"),
        "get_options": ("obj.set_options(['One','Two'])", "obj.get_options()==['One','Two']"),
        "get_option_count": ("obj.set_options(['One','Two','Three'])", "obj.get_option_count()==3"),
        "get_selected_str": ("obj.set_selected(1,False)", "obj.get_selected_str()=='Beta'"),
    },
    "M5Scale": {"set_mode": ("obj.set_mode(lv.scale.MODE.VERTICAL_LEFT)", "obj.get_mode()==lv.scale.MODE.VERTICAL_LEFT")},
    "M5Slider": {
        "set_range": ("obj.set_range(10,90)", "obj.get_min_value()==10 and obj.get_max_value()==90"),
        "set_value": ("obj.set_value(60,False)", "obj.get_value()==60"),
    },
    "M5Spinbox": {
        "set_digit_format": ("obj.set_digit_format(4,2);obj.set_range(0,100);obj.set_value(12.5)", "abs(obj.get_value()-12.5)<0.001"),
        "set_range": ("obj.set_range(0,80);obj.set_value(60)", "obj.get_value()==60 and obj._max_value==80"),
        "set_value": ("obj.set_value(60)", "obj.get_value()==60"),
        "get_value": ("obj.set_value(60)", "obj.get_value()==60"),
        "set_step": ("obj.set_step(5)", None),
        "value2raw": ("result=obj.value2raw(12.5,4,2)", "result==1250"),
        "raw2value": ("result=obj.raw2value(1250,4,2)", "abs(result-12.5)<0.001"),
        "set_style_border_width": ("obj.set_style_border_width(3,lv.PART.MAIN)", None),
    },
    "M5Spinner": {"set_spinner_color": ("obj.set_spinner_color(0x38B8C8,255,lv.PART.INDICATOR)", "obj.get_style_arc_color(lv.PART.INDICATOR).to_int()==0x38B8C8")},
    "M5Switch": {"set_direction": ("obj.set_direction(1)", None)},
    "M5Table": {
        "set_cell_value": ("obj.set_cell_value(0,0,'Cell A')", "obj.get_cell_value(0,0)=='Cell A'"),
        "get_cell_value": ("obj.set_cell_value(1,1,'Cell B')", "obj.get_cell_value(1,1)=='Cell B'"),
        "set_row_count": ("obj.set_row_count(3)", "obj.get_row_count()==3"),
        "set_column_count": ("obj.set_column_count(3)", "obj.get_column_count()==3"),
        "set_column_width": ("obj.set_column_width(0,80)", "obj.get_column_width(0)==80"),
    },
    "M5TabView": {
        "add_tab": ("child=obj.add_tab('Second')", "obj.tab_num==2"),
        "rename_tab": ("obj.rename_tab(0,'Renamed')", None),
        "get_tab_active": ("obj.add_tab('Second');obj.set_active(1,False)", "obj.get_tab_active()==2"),
    },
    "M5TextArea": {
        "set_one_line": ("obj.set_one_line(True)", "obj.get_one_line()"),
        "set_max_length": ("obj.set_max_length(4);obj.set_text('ABCDEFG')", "obj.get_text()=='ABCD'"),
        "set_text": ("obj.set_text('Updated text')", "obj.get_text()=='Updated text'"),
        "get_text": ("obj.set_text('Getter check')", "obj.get_text()=='Getter check'"),
        "add_text": ("obj.set_text('A');obj.add_text('BC')", "obj.get_text()=='ABC'"),
    },
    "M5Win": {
        "add_title": ("child=obj.add_title('Window title')", None),
        "add_text": ("child=obj.add_text('Window body')", None),
        "add_button": ("child=obj.add_button(text='OK')", None),
    },
}

# Public inherited methods listed by the official UIFlow wrappers are explicit
# recipes too. They are not inferred PASS from a parent class or another host.
COMMON.update({
    "get_x": ("obj.set_x(28);obj.update_layout()", "obj.get_x()==28"),
    "get_y": ("obj.set_y(64);obj.update_layout()", "obj.get_y()==64"),
    "set_style_border_width": ("obj.set_style_border_width(3,lv.PART.MAIN)", "obj.get_style_border_width(lv.PART.MAIN)==3"),
    "set_style_line_width": ("obj.set_style_line_width(3,lv.PART.MAIN)", "obj.get_style_line_width(lv.PART.MAIN)==3"),
})
SPECIFIC["M5Arc"].update({
    "set_rotation": ("obj.set_rotation(45)", "obj.get_rotation()==45"),
    "get_value": ("obj.set_value(60)", "obj.get_value()==60"),
    "set_mode": ("obj.set_mode(lv.arc.MODE.REVERSE)", "obj.get_mode()==lv.arc.MODE.REVERSE"),
})
for _target in ("M5Bar", "M5Slider"):
    SPECIFIC[_target].update({
        "get_value": ("obj.set_value(60,False)", "obj.get_value()==60"),
        "get_min_value": ("obj.set_range(10,90)", "obj.get_min_value()==10"),
        "get_max_value": ("obj.set_range(10,90)", "obj.get_max_value()==90"),
    })
SPECIFIC["M5ButtonMatrix"].update({
    "set_button_width": ("obj.set_button_width(0,2)", None),
    "get_button_text": ("result=obj.get_button_text(0)", "result=='A'"),
    "clear_button_ctrl": ("obj.set_button_ctrl(0,lv.buttonmatrix.CTRL.CHECKABLE);obj.clear_button_ctrl(0,lv.buttonmatrix.CTRL.CHECKABLE)", "not obj.has_button_ctrl(0,lv.buttonmatrix.CTRL.CHECKABLE)"),
    "set_button_ctrl": ("obj.set_button_ctrl(0,lv.buttonmatrix.CTRL.CHECKABLE)", "obj.has_button_ctrl(0,lv.buttonmatrix.CTRL.CHECKABLE)"),
    "set_button_ctrl_all": ("obj.set_button_ctrl_all(lv.buttonmatrix.CTRL.CHECKABLE)", "all(obj.has_button_ctrl(i,lv.buttonmatrix.CTRL.CHECKABLE) for i in range(4))"),
    "clear_button_ctrl_all": ("obj.set_button_ctrl_all(lv.buttonmatrix.CTRL.CHECKABLE);obj.clear_button_ctrl_all(lv.buttonmatrix.CTRL.CHECKABLE)", "all(not obj.has_button_ctrl(i,lv.buttonmatrix.CTRL.CHECKABLE) for i in range(4))"),
    "set_one_checked": ("obj.set_one_checked(True)", "obj.get_one_checked()"),
})
SPECIFIC["M5Calendar"]["set_month_shown"] = ("obj.set_month_shown(2026,11)", "obj.get_showed_date().year==2026 and obj.get_showed_date().month==11")
SPECIFIC["M5Chart"].update({
    "set_type": ("obj.set_type(lv.chart.TYPE.BAR)", "obj.get_type()==lv.chart.TYPE.BAR"),
    "get_type": ("obj.set_type(lv.chart.TYPE.BAR)", "obj.get_type()==lv.chart.TYPE.BAR"),
    "set_point_count": ("obj.set_point_count(7)", "obj.get_point_count()==7"),
    "get_point_count": ("obj.set_point_count(7)", "obj.get_point_count()==7"),
    "set_update_mode": ("obj.set_update_mode(lv.chart.UPDATE_MODE.SHIFT)", None),
    "set_div_line_count": ("obj.set_div_line_count(3,4)", None),
    "remove_series": ("series=obj.add_series(0x38B8C8,lv.chart.AXIS.PRIMARY_Y);obj.remove_series(series)", "obj.get_series_next(None) is None"),
    "hide_series": ("series=obj.add_series(0x38B8C8,lv.chart.AXIS.PRIMARY_Y);obj.set_series_values(series,[10,40,20,80,60]);obj.hide_series(series,True)", None),
    "set_next_value": ("series=obj.add_series(0x38B8C8,lv.chart.AXIS.PRIMARY_Y);obj.set_series_values(series,[10,40,20,80,60]);obj.set_next_value(series,90)", None),
    "get_pressed_point": ("series=obj.add_series(0x38B8C8,lv.chart.AXIS.PRIMARY_Y);obj.set_series_values(series,[10,40,20,80,60]);result=obj.get_pressed_point()", None),
    "set_style_size": ("obj.set_style_size(4,4,lv.PART.INDICATOR)", "obj.get_style_width(lv.PART.INDICATOR)==4 and obj.get_style_height(lv.PART.INDICATOR)==4"),
})
SPECIFIC["M5Checkbox"] = {
    "set_text": ("obj.set_text('Updated checkbox')", "obj.get_text()=='Updated checkbox'"),
    "get_text": ("obj.set_text('Getter check')", "obj.get_text()=='Getter check'"),
}
SPECIFIC["M5Dropdown"].update({
    "get_selected": ("obj.set_selected(1,False)", "obj.get_selected()==1"),
    "set_selected_highlight": ("obj.set_selected_highlight(True)", "obj.get_selected_highlight()"),
    "get_option_count": ("obj.set_options(['Alpha','Beta','Gamma'])", "obj.get_option_count()==3"),
    "get_option_index": ("obj.set_options(['Alpha','Beta','Gamma'])", "obj.get_option_index('Beta')==1"),
    "set_text": ("obj.set_text('Fixed caption')", "obj.get_text()=='Fixed caption'"),
    "get_text": ("obj.set_text('Getter check')", "obj.get_text()=='Getter check'"),
})
SPECIFIC["M5Keyboard"] = {
    "set_textarea": ("obj.set_textarea(textarea)", "obj.get_textarea()==textarea"),
    "get_textarea": ("obj.set_textarea(textarea)", "obj.get_textarea()==textarea"),
    "set_mode": ("obj.set_mode(lv.keyboard.MODE.TEXT_UPPER)", "obj.get_mode()==lv.keyboard.MODE.TEXT_UPPER"),
    "get_mode": ("obj.set_mode(lv.keyboard.MODE.TEXT_UPPER)", "obj.get_mode()==lv.keyboard.MODE.TEXT_UPPER"),
    "set_popovers": ("obj.set_popovers(True)", "obj.get_popovers()"),
    "get_selected_button": ("result=obj.get_selected_button()", None),
    "get_button_text": ("result=obj.get_button_text(0)", None),
}
SPECIFIC["M5LED"].update({
    "on": ("obj.on()", "obj.get_brightness()==100"),
    "off": ("obj.off()", "obj.get_brightness()==0"),
    "toggle": ("obj.off();obj.toggle()", "obj.get_brightness()==100"),
})
SPECIFIC["M5List"].update({
    "move_background": ("sibling=m5ui.M5Label('Sibling',parent=page);obj.move_background()", "obj.get_index()==0"),
    "move_foreground": ("sibling=m5ui.M5Label('Sibling',parent=page);obj.move_foreground()", "obj.get_index()==page.get_child_count()-1"),
    "move_to_index": ("obj.move_to_index(0)", "obj.get_index()==0"),
    "delete": ("obj.delete()", "expected_deleted"),
})
SPECIFIC["M5Menu"].update({
    "set_page": ("new_page=lv.menu_page(obj,'Second');obj.set_page(new_page)", "obj.get_cur_main_page()==new_page"),
    "set_mode_header": ("obj.set_mode_header(lv.menu.HEADER.TOP_FIXED)", None),
})
SPECIFIC["M5Msgbox"].update({"add_close_button": ("child=obj.add_close_button()", None),"delete": ("obj.delete()", "expected_deleted")})
SPECIFIC["M5Win"]["delete"] = ("obj.delete()", "expected_deleted")
SPECIFIC["M5Roller"].update({
    "get_selected": ("obj.set_selected(1,False)", "obj.get_selected()==1"),
    "set_visible_row_count": ("obj.set_visible_row_count(3)", None),
})
SPECIFIC["M5Scale"].update({
    "set_size": ("obj.set_size(160,64);obj.update_layout()", "obj.get_width()==160 and obj.get_height()==20 and obj.wrapper.get_width()==180 and obj.wrapper.get_height()==40"),
    "set_pos": ("obj.set_pos(24,56);obj.update_layout()", "obj.wrapper.get_x()==24 and obj.wrapper.get_y()==56"),
    "set_x": ("obj.set_x(28);obj.update_layout()", "obj.wrapper.get_x()==28"),
    "set_y": ("obj.set_y(64);obj.update_layout()", "obj.wrapper.get_y()==64"),
    "set_range": ("obj.set_range(10,90)", "obj.get_range_min_value()==10 and obj.get_range_max_value()==90"),
    "set_major_tick_every": ("obj.set_major_tick_every(5)", "obj.get_major_tick_every()==5"),
    "set_total_tick_count": ("obj.set_total_tick_count(21)", "obj.get_total_tick_count()==21"),
    "set_label_show": ("obj.set_label_show(False)", "not obj.get_label_show()"),
    "set_text_src": ("obj.set_text_src(['Low','Mid','High',None])", None),
})
SPECIFIC["M5Slider"]["set_mode"] = ("obj.set_mode(lv.slider.MODE.RANGE)", "obj.get_mode()==lv.slider.MODE.RANGE")
SPECIFIC["M5Spinner"]["set_anim_params"] = ("obj.set_anim_params(1000,90)", None)
SPECIFIC["M5Switch"]["has_state"] = ("obj.add_state(lv.STATE.CHECKED)", "obj.has_state(lv.STATE.CHECKED)")
SPECIFIC["M5Table"].update({
    "get_row_count": ("obj.set_row_count(3)", "obj.get_row_count()==3"),
    "get_column_count": ("obj.set_column_count(3)", "obj.get_column_count()==3"),
    "get_column_width": ("obj.set_column_width(0,80)", "obj.get_column_width(0)==80"),
})
SPECIFIC["M5TextArea"].update({
    "set_placeholder_text": ("obj.set_text('');obj.set_placeholder_text('Placeholder')", "obj.get_placeholder_text()=='Placeholder'"),
    "set_style_text_align": ("obj.set_style_text_align(lv.TEXT_ALIGN.RIGHT,lv.PART.MAIN)", "obj.get_style_text_align(lv.PART.MAIN)==lv.TEXT_ALIGN.RIGHT"),
    "set_password_mode": ("obj.set_password_mode(True)", "obj.get_password_mode()"),
    "set_accepted_chars": ("obj.set_text('');obj.set_accepted_chars('0123456789');obj.add_text('A1B2C3')", "obj.get_text()=='123'"),
})
SPECIFIC["M5Spinbox"].update({
    "set_state": ("obj.set_state(lv.STATE.DISABLED,True)", "all(child.has_state(lv.STATE.DISABLED) for child in (obj._spinbox,obj._btn_dec,obj._btn_inc))"),
    "toggle_state": ("obj.set_state(lv.STATE.DISABLED,False);obj.toggle_state(lv.STATE.DISABLED)", "all(child.has_state(lv.STATE.DISABLED) for child in (obj._spinbox,obj._btn_dec,obj._btn_inc))"),
    "set_bg_color": ("obj.set_bg_color(0x304850,255,lv.PART.MAIN)", "obj._spinbox.get_style_bg_color(lv.PART.MAIN).to_int()==0x304850"),
    "set_border_color": ("obj.set_border_color(0x38B8C8,255,lv.PART.MAIN)", "obj._spinbox.get_style_border_color(lv.PART.MAIN).to_int()==0x38B8C8"),
    "set_style_border_width": ("obj.set_style_border_width(3,lv.PART.MAIN)", "obj._spinbox.get_style_border_width(lv.PART.MAIN)==3"),
    "set_style_radius": ("obj.set_style_radius(6,lv.PART.MAIN)", "obj._spinbox.get_style_radius(lv.PART.MAIN)==6"),
    "set_step": ("obj.set_step(5)", "obj._spinbox.get_step()==5"),
})


GUEST_COMMON = '''import time, json, sys, os
import M5
from M5 import *
CASE_ID = %r
API_TARGET = %r
def emit(kind, **data):
    data['case_id'] = CASE_ID
    data['api_target'] = API_TARGET
    print('M5EMU_UI_' + kind + ' ' + json.dumps(data))
def settle():
    for _ in range(20):
        M5.update()
        time.sleep_ms(20)
M5.begin()
try:
    # Display recipes compare requested colors with rendered pixels. Normalize
    # panel backlight to full scale so a persisted user brightness is not
    # misreported as a display-controller color error.
    M5.Lcd.setBrightness(255)
except Exception as error:
    emit('BRIGHTNESS_NORMALIZATION',status='ERROR',error=repr(error))
try:
    # UI recipes use the unrotated native coordinate system. Current UIFlow2
    # images may persist rotation=1 across the startup menu.
    M5.Lcd.setRotation(0)
except Exception as error:
    emit('ROTATION_NORMALIZATION',status='ERROR',error=repr(error))
emit('ENV', board=M5.getBoard(),width=M5.Lcd.width(),height=M5.Lcd.height(),rotation=M5.Lcd.getRotation())
'''


# The known color patch is a data-plane oracle: the host must compare the
# requested point/region in a fresh frame, allowing only RGB565 quantization.
DISPLAY_RECIPES = {
    "width": ("value=obj.width()", "value==expected_width", None),
    "height": ("value=obj.height()", "value==expected_height", None),
    "getRotation": ("obj.setRotation(1);value=obj.getRotation()", "value==1", None),
    "setRotation": ("obj.setRotation(1)", "obj.getRotation()==1", None),
    "getColorDepth": ("value=obj.getColorDepth()", "value in (1,2,4,8,16,24,32)", None),
    "setColorDepth": ("obj.setColorDepth(16)", "obj.getColorDepth()==16", None),
    "getCursor": ("obj.setCursor(24,68);value=obj.getCursor()", "tuple(value)==(24,68)", None),
    "setCursor": ("obj.setCursor(24,68)", "tuple(obj.getCursor())==(24,68)", None),
    "isEPD": ("value=obj.isEPD()", "value is False", None),
    "getBrightness": ("value=obj.getBrightness()", "isinstance(value,int) and 0<=value<=255", None),
    "setBrightness": ("obj.setBrightness(192)", "obj.getBrightness()==192", None),
    "setFont": ("obj.setFont(M5.Lcd.FONTS.DejaVu18);obj.drawString('Font check',20,60)", None, {"kind": "text", "text": "Font check", "box": [20,60,220,90]}),
    "setTextSize": ("obj.setTextSize(2);obj.drawString('Size 2',20,60)", None, {"kind": "text", "text": "Size 2", "box": [20,60,220,100]}),
    "setTextColor": ("obj.setTextColor(0x38B8C8,0x0B1014);obj.drawString('Color',20,60)", None, {"kind": "text_color", "text": "Color", "rgb": 0x38B8C8, "box": [20,60,180,90]}),
    "clear": ("obj.clear(0x38B8C8)", None, {"kind": "pixels", "points": [[30,70,0x38B8C8],[150,120,0x38B8C8]]}),
    "fillScreen": ("obj.fillScreen(0x38B8C8)", None, {"kind": "pixels", "points": [[30,70,0x38B8C8],[150,120,0x38B8C8]]}),
    "drawPixel": ("obj.drawPixel(40,70,0x38B8C8)", None, {"kind": "pixels", "points": [[40,70,0x38B8C8]]}),
    "drawCircle": ("obj.drawCircle(100,100,30,0x38B8C8)", None, {"kind": "pixels", "points": [[100,70,0x38B8C8],[70,100,0x38B8C8]]}),
    "fillCircle": ("obj.fillCircle(100,100,30,0x38B8C8)", None, {"kind": "pixels", "points": [[100,100,0x38B8C8],[110,110,0x38B8C8]]}),
    "drawEllipse": ("obj.drawEllipse(100,100,50,30,0x38B8C8)", None, {"kind": "pixels", "points": [[100,70,0x38B8C8],[50,100,0x38B8C8]]}),
    "fillEllipse": ("obj.fillEllipse(100,100,50,30,0x38B8C8)", None, {"kind": "pixels", "points": [[100,100,0x38B8C8],[120,110,0x38B8C8]]}),
    "drawLine": ("obj.drawLine(20,70,220,70,0x38B8C8)", None, {"kind": "pixels", "points": [[40,70,0x38B8C8],[200,70,0x38B8C8]]}),
    "drawRect": ("obj.drawRect(20,60,160,80,0x38B8C8)", None, {"kind": "pixels", "points": [[20,60,0x38B8C8],[20,100,0x38B8C8]]}),
    "fillRect": ("obj.fillRect(20,60,160,80,0x38B8C8)", None, {"kind": "pixels", "points": [[40,70,0x38B8C8],[150,120,0x38B8C8]]}),
    "drawRoundRect": ("obj.drawRoundRect(20,60,160,80,8,0x38B8C8)", None, {"kind": "pixels", "points": [[60,60,0x38B8C8],[20,100,0x38B8C8]]}),
    "fillRoundRect": ("obj.fillRoundRect(20,60,160,80,8,0x38B8C8)", None, {"kind": "pixels", "points": [[40,70,0x38B8C8],[150,120,0x38B8C8]]}),
    "drawTriangle": ("obj.drawTriangle(20,140,100,60,180,140,0x38B8C8)", None, {"kind": "pixels", "points": [[100,60,0x38B8C8],[100,140,0x38B8C8]]}),
    "fillTriangle": ("obj.fillTriangle(20,140,100,60,180,140,0x38B8C8)", None, {"kind": "pixels", "points": [[100,100,0x38B8C8],[100,120,0x38B8C8]]}),
    "drawArc": ("obj.drawArc(100,100,40,30,0,180,0x38B8C8)", None, {"kind": "shape", "shape": "outlined lower semicircle", "box": [60,100,140,140]}),
    "fillArc": ("obj.fillArc(100,100,40,30,0,180,0x38B8C8)", None, {"kind": "shape", "shape": "filled lower semicircle ring", "box": [60,100,140,140]}),
    "drawEllipseArc": ("obj.drawEllipseArc(120,100,60,40,30,20,0,180,0x38B8C8)", None, {"kind": "shape", "shape": "elliptical lower arc", "box": [60,100,180,140]}),
    "fillEllipseArc": ("obj.fillEllipseArc(120,100,60,40,30,20,0,180,0x38B8C8)", None, {"kind": "shape", "shape": "elliptical lower filled arc", "box": [60,100,180,140]}),
    "drawQR": ("obj.drawQR('UIFLOW2-API',40,60,120,3)", None, {"kind": "qr_decode", "text": "UIFLOW2-API", "box": [40,60,160,180]}),
    "drawPng": ("obj.drawPng(__import__('os').getcwd()+'/fixture.png',40,60)", None, {"kind": "pixels", "points": [[42,62,0xFF0000],[52,62,0x00FF00],[42,72,0x0000FF],[52,72,0xFFFF00]]}),
    "drawBmp": ("obj.drawBmp(__import__('os').getcwd()+'/fixture.bmp',40,60)", None, {"kind": "pixels", "points": [[42,62,0xFF0000],[52,62,0x00FF00],[42,72,0x0000FF],[52,72,0xFFFF00]]}),
    "drawImage": ("obj.drawImage(__import__('os').getcwd()+'/fixture.png',40,60)", None, {"kind": "pixels", "points": [[42,62,0xFF0000],[52,62,0x00FF00],[42,72,0x0000FF],[52,72,0xFFFF00]]}),
    "drawRawBuf": ("raw=bytearray([0xF8,0x00]*256);obj.drawRawBuf(raw,40,60,16,16,len(raw),False)", None, {"kind": "pixels", "points": [[42,62,0xFF0000],[52,72,0xFF0000]]}),
    "drawString": ("obj.drawString('UIFlow API',20,60)", None, {"kind": "text", "text": "UIFlow API", "box": [20,60,240,90]}),
    "drawCenterString": ("obj.drawCenterString('Centered',120,60)", None, {"kind": "text_center", "text": "Centered", "center_x": 120, "box": [20,60,220,90]}),
    "drawRightString": ("obj.drawRightString('Right',220,60)", None, {"kind": "text_right", "text": "Right", "right_x": 220, "box": [20,60,220,90]}),
    "print": ("obj.setCursor(20,60);obj.print('Print API')", None, {"kind": "text", "text": "Print API", "box": [20,60,240,90]}),
    "printf": ("obj.setCursor(20,60);obj.printf('Value=%d',42)", None, {"kind": "text", "text": "Value=42", "box": [20,60,240,90]}),
    "textWidth": ("obj.setFont(M5.Lcd.FONTS.DejaVu18);a=obj.textWidth('A');b=obj.textWidth('AAAA')", "a>0 and b>a*2", None),
    "fontHeight": ("obj.setFont(M5.Lcd.FONTS.DejaVu18);value=obj.fontHeight()", "value>0 and value<64", None),
    "newCanvas": ("child=obj.newCanvas(100,60,16,True);child.fillScreen(0x38B8C8);child.push(20,60)", "child.width()==100 and child.height()==60", {"kind": "pixels", "points": [[40,70,0x38B8C8]]}),
    "startWrite": ("obj.startWrite();obj.fillRect(20,60,160,80,0x38B8C8);obj.endWrite()", None, {"kind": "pixels", "points": [[40,70,0x38B8C8]]}),
    "endWrite": ("obj.startWrite();obj.fillRect(20,60,160,80,0x38B8C8);obj.endWrite()", None, {"kind": "pixels", "points": [[40,70,0x38B8C8]]}),
    "push": ("obj.fillRect(20,60,160,80,0x38B8C8);obj.push(0,0)", None, {"kind": "pixels", "points": [[40,70,0x38B8C8]]}),
}

DISPLAY_UNASSIGNED_REASONS = {
    "getEpdMode": "CoreS3 is LCD; classify EPD-only behavior on compatible display separately",
    "setEpdMode": "CoreS3 is LCD; classify EPD-only behavior on compatible display separately",
    "loadFont": "Requires an official compatible external-font fixture and glyph oracle",
    "unloadFont": "Requires an official compatible external-font fixture and restoration oracle",
    "drawJpg": "Requires packaged JPEG fixture with decoded color/bounds oracle",
    "drawPixels": "Native argument schema and pixel buffer ownership need a binding-specific recipe",
    "setTextScroll": "Needs overflow stream sequence plus clipped/scroll region oracle",
    "powerSaveOn": "Panel power state needs controller readback; framebuffer bytes alone do not prove panel power",
    "powerSaveOff": "Panel power state needs controller readback; framebuffer bytes alone do not prove panel power",
    "show": "Requires camera/image object and same-session controller data-plane fixture",
    "writeCommand": "Requires panel-specific register/write protocol and readback oracle",
    "writeCommand16": "Requires panel-specific register/write protocol and readback oracle",
    "writeData": "Requires panel-specific register/write protocol and readback oracle",
    "writeData16": "Requires panel-specific register/write protocol and readback oracle",
    "writeData32": "Requires panel-specific register/write protocol and readback oracle",
    "readData": "Requires panel-specific register/write protocol and readback oracle",
    "readData16": "Requires panel-specific register/write protocol and readback oracle",
    "readData32": "Requires panel-specific register/write protocol and readback oracle",
    "read": "Stream protocol requires bounded RX fixture; unbounded read may hang",
    "write": "Stream protocol requires rendered/cursor and bytes-written oracle",
    "close": "Requires a dedicated lifecycle-ending program",
    "delete": "Canvas deletion requires separate post-delete negative control; cannot retain rendered object",
}
DISPLAY_RECIPES.update({
    "drawPixels": ("obj.drawPixels([[40,70],[80,90]],color=0x38B8C8)", None, {"kind":"pixels","points":[[40,70,0x38B8C8],[80,90,0x38B8C8]]}),
    "drawJpg": ("obj.drawJpg(__import__('os').getcwd()+'/fixture.jpg',40,60)", None, {"kind":"pixels","points":[[42,62,0xFF0000],[52,62,0x00FF00],[42,72,0x0000FF],[52,72,0xFFFF00]]}),
    "setTextScroll": ("obj.setTextSize(2);obj.setTextScroll(True);obj.setCursor(0,216);obj.print(''.join('SCROLL %d\\n'%i for i in range(20)))", None, {"kind":"text","text":"SCROLL 19","box":[0,160,320,240]}),
})


def display_recipe_for(method: str, width: int, height: int):
    """Adapt the 320x240 recipe canvas to the selected board geometry.

    Coordinates represent the desktop-sized demonstration canvas. Scaling
    both the drawing calls and their frame oracles keeps a narrow StickS3 or
    circular StopWatch from producing harness-only out-of-bounds failures.
    Text glyph size and image pixel dimensions remain native inputs.
    """
    if method not in DISPLAY_RECIPES:
        return None
    # The only square panel in the current inventory is the circular
    # StopWatch glass. Keep its transformed drawing rectangle inside the
    # inscribed visible circle.
    margin = 0.9 if width == height else 1.0
    x_scale = width / 320 * margin
    y_scale = height / 240 * margin
    sx = lambda x: max(0, min(width - 1, int(round(width / 2 + (x - 160) * x_scale))))
    sy = lambda y: max(0, min(height - 1, int(round(height / 2 + (y - 120) * y_scale))))
    sw = lambda value: max(1, int(round(value * x_scale)))
    sh = lambda value: max(1, int(round(value * y_scale)))
    sr = lambda value: max(1, int(round(value * min(x_scale, y_scale))))
    p = lambda x, y: [sx(x), sy(y)]
    box = lambda x0, y0, x1, y1: [sx(x0), sy(y0), sx(x1), sy(y1)]
    image_points = lambda x, y: [
        [sx(x) + 2, sy(y) + 2, 0xFF0000],
        [sx(x) + 11, sy(y) + 2, 0x00FF00],
        [sx(x) + 2, sy(y) + 11, 0x0000FF],
        [sx(x) + 11, sy(y) + 11, 0xFFFF00],
    ]
    color = "0x38B8C8"
    qr_size = min(sw(120), sh(120))
    actions = {
        "getCursor": f"obj.setCursor({sx(24)},{sy(68)});value=obj.getCursor()",
        "setCursor": f"obj.setCursor({sx(24)},{sy(68)})",
        "setFont": f"obj.setFont(M5.Lcd.FONTS.DejaVu18);obj.drawString('Font check',{sx(20)},{sy(60)})",
        "setTextSize": f"obj.setTextSize(2);obj.drawString('Size 2',{sx(20)},{sy(60)})",
        "setTextColor": f"obj.setTextColor({color},0x0B1014);obj.drawString('Color',{sx(20)},{sy(60)})",
        "clear": f"obj.clear({color})",
        "fillScreen": f"obj.fillScreen({color})",
        "drawPixel": f"obj.drawPixel({sx(40)},{sy(70)},{color})",
        "drawCircle": f"obj.drawCircle({sx(100)},{sy(100)},{sr(30)},{color})",
        "fillCircle": f"obj.fillCircle({sx(100)},{sy(100)},{sr(30)},{color})",
        "drawEllipse": f"obj.drawEllipse({sx(100)},{sy(100)},{sw(50)},{sh(30)},{color})",
        "fillEllipse": f"obj.fillEllipse({sx(100)},{sy(100)},{sw(50)},{sh(30)},{color})",
        "drawLine": f"obj.drawLine({sx(20)},{sy(70)},{sx(220)},{sy(70)},{color})",
        "drawRect": f"obj.drawRect({sx(20)},{sy(60)},{sw(160)},{sh(80)},{color})",
        "fillRect": f"obj.fillRect({sx(20)},{sy(60)},{sw(160)},{sh(80)},{color})",
        "drawRoundRect": f"obj.drawRoundRect({sx(20)},{sy(60)},{sw(160)},{sh(80)},{sr(8)},{color})",
        "fillRoundRect": f"obj.fillRoundRect({sx(20)},{sy(60)},{sw(160)},{sh(80)},{sr(8)},{color})",
        "drawTriangle": f"obj.drawTriangle({sx(20)},{sy(140)},{sx(100)},{sy(60)},{sx(180)},{sy(140)},{color})",
        "fillTriangle": f"obj.fillTriangle({sx(20)},{sy(140)},{sx(100)},{sy(60)},{sx(180)},{sy(140)},{color})",
        "drawArc": f"obj.drawArc({sx(100)},{sy(100)},{sw(40)},{sh(30)},0,180,{color})",
        "fillArc": f"obj.fillArc({sx(100)},{sy(100)},{sw(40)},{sh(30)},0,180,{color})",
        "drawEllipseArc": f"obj.drawEllipseArc({sx(120)},{sy(100)},{sw(60)},{sh(40)},{sr(30)},{sr(20)},0,180,{color})",
        "fillEllipseArc": f"obj.fillEllipseArc({sx(120)},{sy(100)},{sw(60)},{sh(40)},{sr(30)},{sr(20)},0,180,{color})",
        "drawQR": f"obj.drawQR('UIFLOW2-API',{sx(40)},{sy(60)},{qr_size},3)",
        "drawPng": f"obj.drawPng('/flash/api-sweep-fixture.png',{sx(40)},{sy(60)})",
        "drawBmp": f"obj.drawBmp('/flash/api-sweep-fixture.bmp',{sx(40)},{sy(60)})",
        "drawImage": f"obj.drawImage('/flash/api-sweep-fixture.png',{sx(40)},{sy(60)})",
        "drawRawBuf": f"raw=bytearray([0xF8,0x00]*256);obj.drawRawBuf(raw,{sx(40)},{sy(60)},16,16,256,False)",
        "drawString": f"obj.drawString('UIFlow API',{sx(20)},{sy(60)})",
        "drawCenterString": f"obj.drawCenterString('Centered',{sx(120)},{sy(60)})",
        "drawRightString": f"obj.drawRightString('Right',{sx(220)},{sy(60)})",
        "print": f"obj.setCursor({sx(20)},{sy(60)});obj.print('Print API')",
        "printf": f"obj.setCursor({sx(20)},{sy(60)});obj.printf('Value=%d',42)",
        "drawPixels": f"obj.drawPixels([{p(40,70)},{p(80,90)}],color={color})",
        "drawJpg": f"obj.drawJpg('/flash/api-sweep-fixture.jpg',{sx(40)},{sy(60)})",
        "startWrite": f"obj.startWrite();obj.fillRect({sx(20)},{sy(60)},{sw(160)},{sh(80)},{color});obj.endWrite()",
        "endWrite": f"obj.startWrite();obj.fillRect({sx(20)},{sy(60)},{sw(160)},{sh(80)},{color});obj.endWrite()",
        "push": f"obj.fillRect({sx(20)},{sy(60)},{sw(160)},{sh(80)},{color});obj.push(0,0)",
        "setTextScroll": f"obj.setTextSize(1);obj.setTextScroll(True);obj.setCursor(0,{max(0,height-20)});obj.print(''.join('SCROLL %d\\n'%i for i in range(20)))",
        "newCanvas": (
            f"canvas_width={sw(100)};canvas_height={sh(60)};"
            f"child=obj.newCanvas(canvas_width,canvas_height,16,True);"
            f"child.fillScreen({color});child.push({sx(20)},{sy(60)})"
        ),
    }
    predicates = {
        "getCursor": f"tuple(value)==({sx(24)},{sy(68)})",
        "setCursor": f"tuple(obj.getCursor())==({sx(24)},{sy(68)})",
        "newCanvas": "child.width()==canvas_width and child.height()==canvas_height",
    }
    frames = {
        "clear": {"kind": "pixels", "points": [[*p(30, 70), 0x38B8C8], [*p(150, 120), 0x38B8C8]]},
        "fillScreen": {"kind": "pixels", "points": [[*p(30, 70), 0x38B8C8], [*p(150, 120), 0x38B8C8]]},
        "drawPixel": {"kind": "pixels", "points": [[*p(40, 70), 0x38B8C8]]},
        "drawCircle": {"kind": "pixels", "points": [
            [sx(100), sy(100) - sr(30), 0x38B8C8],
            [sx(100) - sr(30), sy(100), 0x38B8C8],
        ]},
        "fillCircle": {"kind": "pixels", "points": [
            [sx(100), sy(100), 0x38B8C8],
            [sx(100) + sr(10), sy(100) + sr(10), 0x38B8C8],
        ]},
        "drawEllipse": {"kind": "pixels", "points": [
            [sx(100), sy(100) - sh(30), 0x38B8C8],
            [sx(100) - sw(50), sy(100), 0x38B8C8],
        ]},
        "fillEllipse": {"kind": "pixels", "points": [
            [sx(100), sy(100), 0x38B8C8],
            [sx(100) + sw(20), sy(100) + sh(10), 0x38B8C8],
        ]},
        "drawLine": {"kind": "pixels", "points": [[*p(40, 70), 0x38B8C8], [*p(200, 70), 0x38B8C8]]},
        "drawRect": {"kind": "pixels", "points": [[*p(20, 60), 0x38B8C8], [*p(20, 100), 0x38B8C8]]},
        "fillRect": {"kind": "pixels", "points": [[*p(40, 70), 0x38B8C8], [*p(150, 120), 0x38B8C8]]},
        "drawRoundRect": {"kind": "pixels", "points": [[*p(60, 60), 0x38B8C8], [*p(20, 100), 0x38B8C8]]},
        "fillRoundRect": {"kind": "pixels", "points": [[*p(40, 70), 0x38B8C8], [*p(150, 120), 0x38B8C8]]},
        "drawTriangle": {"kind": "pixels", "points": [[*p(100, 60), 0x38B8C8], [*p(100, 140), 0x38B8C8]]},
        "fillTriangle": {"kind": "pixels", "points": [[*p(100, 100), 0x38B8C8], [*p(100, 120), 0x38B8C8]]},
        "drawArc": {"kind": "shape", "shape": "outlined lower semicircle", "box": box(60, 100, 140, 140)},
        "fillArc": {"kind": "shape", "shape": "filled lower semicircle ring", "box": box(60, 100, 140, 140)},
        "drawEllipseArc": {"kind": "shape", "shape": "elliptical lower arc", "box": box(60, 100, 180, 140)},
        "fillEllipseArc": {"kind": "shape", "shape": "elliptical lower filled arc", "box": box(60, 100, 180, 140)},
        "drawQR": {"kind": "qr_decode", "text": "UIFLOW2-API",
                   "box": [sx(40), sy(60), sx(40) + qr_size, sy(60) + qr_size]},
        "drawPng": {"kind": "pixels", "points": image_points(40, 60)},
        "drawBmp": {"kind": "pixels", "points": image_points(40, 60)},
        "drawImage": {"kind": "pixels", "points": image_points(40, 60)},
        "drawJpg": {"kind": "pixels", "points": image_points(40, 60)},
        "drawRawBuf": {"kind": "pixels", "points": [[sx(40) + 2, sy(60) + 2, 0xFF0000],
                                                    [sx(40) + 11, sy(60) + 11, 0xFF0000]]},
        "drawString": {"kind": "text", "text": "UIFlow API", "box": box(20, 60, 240, 90)},
        "drawCenterString": {"kind": "text_center", "text": "Centered", "center_x": sx(120),
                             "box": box(20, 60, 220, 90)},
        "drawRightString": {"kind": "text_right", "text": "Right", "right_x": sx(220),
                            "box": box(20, 60, 220, 90)},
        "print": {"kind": "text", "text": "Print API", "box": box(20, 60, 240, 90)},
        "printf": {"kind": "text", "text": "Value=42", "box": box(20, 60, 240, 90)},
        "drawPixels": {"kind": "pixels", "points": [[*p(40, 70), 0x38B8C8], [*p(80, 90), 0x38B8C8]]},
        "setFont": {"kind": "text", "text": "Font check", "box": box(20, 60, 220, 90)},
        "setTextSize": {"kind": "text", "text": "Size 2", "box": box(20, 60, 220, 100)},
        "setTextColor": {"kind": "text_color", "text": "Color", "rgb": 0x38B8C8, "box": box(20, 60, 180, 90)},
        "newCanvas": {"kind": "pixels", "points": [[sx(40), sy(70), 0x38B8C8]]},
        "startWrite": {"kind": "pixels", "points": [[sx(40), sy(70), 0x38B8C8]]},
        "endWrite": {"kind": "pixels", "points": [[sx(40), sy(70), 0x38B8C8]]},
        "push": {"kind": "pixels", "points": [[sx(40), sy(70), 0x38B8C8]]},
        "setTextScroll": {"kind": "text", "text": "SCROLL 19", "box": [0, max(0, height - 60), width, height]},
    }
    action, predicate, frame = DISPLAY_RECIPES[method]
    if method in actions:
        action = actions[method]
    if method in predicates:
        predicate = predicates[method]
    if method in frames:
        frame = frames[method]
    return action, predicate, frame


WIDGET_CONSTRUCTORS = {
    "Label": "Widgets.Label('Widget label',24,68,1.0,0xF3F7F8,0x0B1014,Widgets.FONTS.DejaVu18)",
    "Title": "Widgets.Title('Widget title',8,0xF3F7F8,0x304850,Widgets.FONTS.DejaVu18)",
    "Image": "Widgets.Image(__import__('os').getcwd()+'/fixture.png',40,60)",
    "Line": "Widgets.Line(20,60,220,140,0x38B8C8)",
    "Circle": "Widgets.Circle(120,100,40,0x38B8C8,0x38B8C8)",
    "Rectangle": "Widgets.Rectangle(20,60,160,80,0x38B8C8,0x38B8C8)",
    "Triangle": "Widgets.Triangle(20,140,120,60,220,140,0x38B8C8,0x38B8C8)",
    "QRCode": "Widgets.QRCode('UIFLOW2-API',40,60,120,3)",
}

WIDGET_RECIPES = {
    "Label": {"setText": "obj.setText('Updated label')", "setColor": "obj.setColor(0x38B8C8,0x0B1014)", "setCursor": "obj.setCursor(40,80)", "setSize": "obj.setSize(1.5)", "setFont": "obj.setFont(Widgets.FONTS.DejaVu12)", "setVisible": "obj.setVisible(False)"},
    "Title": {"setText": "obj.setText('Updated title')", "setColor": "obj.setColor(0x38B8C8,0x304850)", "setSize": "obj.setSize(40)", "setTextCursor": "obj.setTextCursor(28)", "setVisible": "obj.setVisible(False)"},
    "Image": {"setImage": "obj.setImage(__import__('os').getcwd()+'/fixture-alt.png')", "setCursor": "obj.setCursor(80,100)", "setVisible": "obj.setVisible(False)", "setScale": "obj.setScale(2.0,2.0)"},
    "Line": {"setColor": "obj.setColor(0x58C78A)", "setPoints": "obj.setPoints(20,140,220,60)", "setVisible": "obj.setVisible(False)"},
    "Circle": {"setColor": "obj.setColor(0x58C78A,0x58C78A)", "setCursor": "obj.setCursor(160,120)", "setRadius": "obj.setRadius(55)", "setVisible": "obj.setVisible(False)"},
    "Rectangle": {"setColor": "obj.setColor(0x58C78A,0x58C78A)", "setCursor": "obj.setCursor(80,100)", "setSize": "obj.setSize(100,60)", "setVisible": "obj.setVisible(False)"},
    "Triangle": {"setColor": "obj.setColor(0x58C78A,0x58C78A)", "setPoints": "obj.setPoints(40,160,140,80,240,160)", "setVisible": "obj.setVisible(False)"},
    "QRCode": {"setText": "obj.setText('UPDATED-API')", "setCursor": "obj.setCursor(80,80)", "setSize": "obj.setSize(100)", "setVersion": "obj.setVersion(4)", "setVisible": "obj.setVisible(False)"},
}


def widget_coordinates(width, height):
    margin = 0.9 if width == height else 1.0
    x_scale = width / 320 * margin
    y_scale = height / 240 * margin
    return {
        "sx": lambda x: max(0, min(width - 1, int(round(width / 2 + (x - 160) * x_scale)))),
        "sy": lambda y: max(0, min(height - 1, int(round(height / 2 + (y - 120) * y_scale)))),
        "sw": lambda value: max(1, int(round(value * x_scale))),
        "sh": lambda value: max(1, int(round(value * y_scale))),
        "sr": lambda value: max(1, int(round(value * min(x_scale, y_scale)))),
    }


def widget_constructor(target, width, height):
    c = widget_coordinates(width, height)
    return {
        "Label": f"Widgets.Label('Widget label',{c['sx'](24)},{c['sy'](68)},1.0,0xF3F7F8,0x0B1014,Widgets.FONTS.DejaVu18)",
        "Title": f"Widgets.Title('Widget title',{c['sx'](8)},0xF3F7F8,0x304850,Widgets.FONTS.DejaVu18)",
        "Image": f"Widgets.Image(__import__('os').getcwd()+'/fixture.png',{c['sx'](40)},{c['sy'](60)})",
        "Line": f"Widgets.Line({c['sx'](20)},{c['sy'](60)},{c['sx'](220)},{c['sy'](140)},0x38B8C8)",
        "Circle": f"Widgets.Circle({c['sx'](120)},{c['sy'](100)},{c['sr'](40)},0x38B8C8,0x38B8C8)",
        "Rectangle": f"Widgets.Rectangle({c['sx'](20)},{c['sy'](60)},{c['sw'](160)},{c['sh'](80)},0x38B8C8,0x38B8C8)",
        "Triangle": f"Widgets.Triangle({c['sx'](20)},{c['sy'](140)},{c['sx'](120)},{c['sy'](60)},{c['sx'](220)},{c['sy'](140)},0x38B8C8,0x38B8C8)",
        "QRCode": f"Widgets.QRCode('UIFLOW2-API',{c['sx'](40)},{c['sy'](60)},{c['sr'](120)},3)",
    }[target]


def adapt_widget_action(target, method, action, width, height):
    c = widget_coordinates(width, height)
    return {
        ("Label", "setCursor"): f"obj.setCursor({c['sx'](40)},{c['sy'](80)})",
        ("Title", "setTextCursor"): f"obj.setTextCursor({c['sx'](28)})",
        ("Image", "setCursor"): f"obj.setCursor({c['sx'](80)},{c['sy'](100)})",
        ("Line", "setPoints"): f"obj.setPoints({c['sx'](20)},{c['sy'](140)},{c['sx'](220)},{c['sy'](60)})",
        ("Circle", "setCursor"): f"obj.setCursor({c['sx'](160)},{c['sy'](120)})",
        ("Circle", "setRadius"): f"obj.setRadius({c['sr'](55)})",
        ("Rectangle", "setCursor"): f"obj.setCursor({c['sx'](80)},{c['sy'](100)})",
        ("Rectangle", "setSize"): f"obj.setSize({c['sw'](100)},{c['sh'](60)})",
        ("Triangle", "setPoints"): f"obj.setPoints({c['sx'](40)},{c['sy'](160)},{c['sx'](140)},{c['sy'](80)},{c['sx'](240)},{c['sy'](160)})",
        ("QRCode", "setCursor"): f"obj.setCursor({c['sx'](80)},{c['sy'](80)})",
        ("QRCode", "setSize"): f"obj.setSize({c['sr'](100)})",
    }.get((target, method), action)


def fixture_files() -> dict:
    """Deterministic four-quadrant PNG/BMP resources, generated without assets."""
    def png(alternate=False):
        palette = [(255,0,0),(0,255,0),(0,0,255),(255,255,0)]
        if alternate:
            palette = list(reversed(palette))
        pixels = [bytes(sum((list(palette[(x//8)+(y//8)*2]) for x in range(16)), [])) for y in range(16)]
        def chunk(kind, value):
            return struct.pack('>I',len(value))+kind+value+struct.pack('>I',zlib.crc32(kind+value)&0xffffffff)
        return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',16,16,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(b'\0'+row for row in pixels)))+chunk(b'IEND',b'')
    colors = [(255,0,0),(0,255,0),(0,0,255),(255,255,0)]
    bmp_data = b''.join(bytes(sum((list(reversed(colors[(x//8)+(y//8)*2])) for x in range(16)), [])) for y in reversed(range(16)))
    bmp = b'BM'+struct.pack('<IHHI',54+len(bmp_data),0,0,54)+struct.pack('<IiiHHIIiiII',40,16,16,1,24,0,len(bmp_data),2835,2835,0,0)+bmp_data
    files = {"fixture.png":png(),"fixture-alt.png":png(True),"fixture.bmp":bmp}
    files["fixture.gif"] = base64.b64decode("R0lGODlhCAAIAIEAAP8AAAAAAAAAAAAAACH/C05FVFNDQVBFMi4wAwEAAAAh+QQACgAAACwAAAAACAAIAAAIDwABCBxIsKDBgwgTKkwYEAAh+QQBCgABACwAAAAACAAIAIEAAP8AAAAAAAAAAAAIDwABCBxIsKDBgwgTKkwYEAA7")
    # Use a real JPEG encoder and deterministic settings; do not pretend PNG
    # bytes test the JPEG decoder. The host dependency is explicit.
    from PIL import Image
    import io
    jpeg_image = Image.new("RGB", (16,16))
    jpeg_image.putdata([colors[(x//8)+(y//8)*2] for y in range(16) for x in range(16)])
    buffer = io.BytesIO()
    jpeg_image.save(buffer, format="JPEG", quality=100, subsampling=0, optimize=False)
    files["fixture.jpg"] = buffer.getvalue()
    return {name: {"encoding": "base64", "data": base64.b64encode(data).decode()} for name,data in files.items()}


STYLE_TYPE_VALUES = {
    "lv_color_t": "lv.color_hex(0x38B8C8)", "lv_opa_t": "180", "bool": "True",
    "lv_align_t": "lv.ALIGN.TOP_LEFT", "lv_grad_dir_t": "lv.GRAD_DIR.VER",
    "lv_border_side_t": "lv.BORDER_SIDE.FULL", "lv_blend_mode_t": "lv.BLEND_MODE.NORMAL",
    "lv_text_decor_t": "lv.TEXT_DECOR.NONE", "lv_text_align_t": "lv.TEXT_ALIGN.LEFT",
    "lv_base_dir_t": "lv.BASE_DIR.LTR", "lv_flex_flow_t": "lv.FLEX_FLOW.ROW",
    "lv_flex_align_t": "lv.FLEX_ALIGN.START", "lv_grid_align_t": "lv.GRID_ALIGN.START",
    "lv_layout_t": "0", "lv_anim_path_cb_t": "lv.anim_t.path_linear",
}


def native_style_recipes(uiflow_root: Path) -> dict:
    """Derive scalar style setter/getter recipes from the actual LVGL header.

    Pointer/image/font/descriptors require their own lifetime and render oracles;
    they are deliberately returned as pending rather than supplied null fakes.
    """
    header = uiflow_root / "m5stack/cmodules/lv_binding_micropython/lvgl/src/misc/lv_style_gen.h"
    source = header.read_text(encoding="utf-8")
    result = {}
    for name, value_type in re.findall(r"void lv_style_set_(\w+)\(lv_style_t \* style, (.+?) value\);", source):
        value = STYLE_TYPE_VALUES.get(value_type)
        if value_type in ("int32_t", "uint32_t", "uint16_t", "uint8_t"):
            value = str({"width":180,"height":80,"length":180,"x":24,"y":56,"min_width":20,"max_width":300,"min_height":20,"max_height":200,"transform_scale_x":256,"transform_scale_y":256,"bg_main_stop":80,"bg_grad_stop":180}.get(name, 4))
        result[name] = {"value_type": value_type, "value_expression": value, "status": "recipe_assigned" if value is not None else "requires_typed_resource_and_lifetime_recipe", "setter": "set_style_" + name, "getter": "get_style_" + name}
    return result


def build_native_style_program(uiflow_root: Path, case_id: str = "native-styles") -> str:
    recipes = native_style_recipes(uiflow_root)
    lines = [GUEST_COMMON % (case_id, "lvgl.obj.style"), "import m5ui", "import lvgl as lv", "m5ui.init()", "page=m5ui.M5Page(bg_c=0x0B1014)", "obj=lv.obj(page)", "obj.set_pos(40,60);obj.set_size(240,140)", "label=lv.label(obj);label.set_text('Native styles');label.center()", "page.screen_load()", "settle()", "style_recipes=" + repr(list(recipes.values()))]
    lines += ["for recipe in style_recipes:", "    setter=recipe['setter'];getter=recipe['getter']", "    if recipe['value_expression'] is None:", "        emit('RESULT',method=setter,paired_getter=getter,status='NOT_RUN',reason=recipe['status'])", "        continue", "    try:", "        before=getattr(obj,getter)(lv.PART.MAIN)", "        expected=eval(recipe['value_expression'])", "        getattr(obj,setter)(expected,lv.PART.MAIN)", "        observed=getattr(obj,getter)(lv.PART.MAIN)", "        ok=observed.to_int()==expected.to_int() if recipe['value_type']=='lv_color_t' else observed==expected", "        getattr(obj,setter)(before,lv.PART.MAIN)", "        emit('RESULT',method=setter,paired_getter=getter,status='STATE_PASS' if ok else 'FAIL',oracle='typed-set/get-restore',scope='native lvgl.obj only; no inherited class or visual-state claim')", "    except Exception as error:", "        emit('RESULT',method=setter,paired_getter=getter,status='FAIL',error=repr(error))"]
    lines += ["settle()", "emit('READY',status='AWAITING_FRAME',scope='native-lvgl-object-style-implementation')", "try:", "    while True:", "        M5.update()", "        time.sleep_ms(20)", "finally:", "    m5ui.deinit()"]
    return "\n".join(lines) + "\n"


def build_m5ui_program(target: str, methods: list[str], case_id: str, stepwise: bool = False) -> str:
    if target not in M5UI_CONSTRUCTORS:
        raise ValueError(f"Unknown M5UI target {target}")
    prefix = [GUEST_COMMON % (case_id, "m5ui." + target), "import m5ui", "import lvgl as lv", "m5ui.init()"]
    setup = ["page=m5ui.M5Page(bg_c=0x0B1014)",
        "heading=m5ui.M5Label('API '+API_TARGET,x=8,y=8,text_c=0xF3F7F8,parent=page)",
        "textarea=m5ui.M5TextArea(text='A',x=8,y=35,w=304,h=36,parent=page)",
        "textarea.add_flag(lv.obj.FLAG.HIDDEN)",
        "obj=" + M5UI_CONSTRUCTORS[target],
    ]
    if target == "M5Keyboard":
        setup += ["textarea.remove_flag(lv.obj.FLAG.HIDDEN)"]
    if target == "M5TabView":
        setup += ["tab0=obj.add_tab('First')", "tablabel=m5ui.M5Label('First page',parent=tab0)"]
    if target == "M5Table":
        setup += ["obj.set_cell_value(0,0,'A');obj.set_cell_value(0,1,'B');obj.set_cell_value(1,0,'C');obj.set_cell_value(1,1,'D')"]
    setup += ["obj.add_event_cb(on_event,lv.EVENT.ALL,None)", "page.screen_load()"]
    lines = ["events=0", "def on_event(event):", "    global events", "    if event.code in (lv.EVENT.CLICKED,lv.EVENT.VALUE_CHANGED,lv.EVENT.PRESSED,lv.EVENT.RELEASED):", "        events+=1", "        emit('EVENT',code=event.code,count=events,textarea_text=textarea.get_text())", "def create_target():", "    global page,obj,textarea,heading"]
    lines += ["    " + line for line in setup]
    lines += ["create_target()", "settle()", "emit('CONSTRUCTED',status='PENDING_FRAME',class_name=" + repr(target) + ",touch={'x':160,'y':110})"]
    ordered_methods = [method for method in methods if method != "delete"] + (["delete"] if "delete" in methods else [])
    for method in ordered_methods:
        if method in (target, "__init__"):
            continue
        # Every method receives its original constructor state. Otherwise an
        # earlier options/range/size setter can invalidate a later getter's
        # oracle, creating a false firmware failure.
        lines += ["old_page=page", "create_target()", "old_page.delete()", "settle()"]
        recipe = SPECIFIC.get(target, {}).get(method, COMMON.get(method))
        if recipe is None:
            lines.append("emit('RESULT',method=" + repr(method) + ",status='NOT_RUN',reason='No behavior-specific recipe yet')")
            continue
        action, predicate = recipe
        lines += ["try:", "    " + action, "    settle()"]
        if predicate == "expected_not_implemented":
            lines += ["    emit('RESULT',method=" + repr(method) + ",status='FAIL',reason='Expected documented source stub')"]
        elif predicate == "expected_deleted":
            lines += ["    emit('RESULT',method='delete',status='PENDING_FRAME_OBJECT_REMOVAL')", "    obj=None"]
        elif predicate is None:
            lines += ["    emit('RESULT',method=" + repr(method) + ",status='PENDING_FRAME_OR_INPUT',action=" + repr(action) + ")"]
        else:
            lines += ["    ok=bool(" + predicate + ")", "    emit('RESULT',method=" + repr(method) + ",status='STATE_PASS' if ok else 'FAIL',oracle=" + repr(predicate) + ")"]
        lines += ["except Exception as error:"]
        if predicate == "expected_not_implemented":
            lines += ["    emit('RESULT',method=" + repr(method) + ",status='EXPECTED_UNSUPPORTED' if isinstance(error,NotImplementedError) else 'FAIL',error=repr(error))"]
        else:
            lines += ["    emit('RESULT',method=" + repr(method) + ",status='FAIL',error=repr(error))"]
        if stepwise:
            # This reserved bottom-right touch is a real Device Service input
            # through the emulated touch controller. It is test coordination,
            # not a target-widget event oracle. The host captures the frame
            # before sending it and records the coordinates separately.
            lines += ["emit('STEP_READY',method=" + repr(method) + ",next_touch={'x':310,'y':235})", "while True:", "    M5.update()", "    if M5.Touch.getCount() and M5.Touch.getX()>=308 and M5.Touch.getY()>=230:", "        break", "    time.sleep_ms(20)", "while M5.Touch.getCount():", "    M5.update()", "    time.sleep_ms(20)"]
    lines += ["settle()", "emit('READY',status='AWAITING_FRAME_AND_INPUT',method_count=" + str(len(methods)) + ")", "while True:", "    M5.update()", "    time.sleep_ms(20)"]
    # The setup belongs inside cleanup as well: a constructor failure must not
    # leave this test's LVGL timer alive before the next same-VM program.
    return "\n".join(prefix + ["try:"] + ["    " + line for line in lines] + ["finally:", "    m5ui.deinit()", "    emit('CLEANUP',status='DEINIT_RETURNED')"]) + "\n"


def method_recipes(target: str) -> dict:
    """Declared recipes only; no claim that these have run on any firmware."""
    return {name: {"action": action, "state_oracle": predicate, "requires_frame": True, "requires_physical_input": name in ("add_event_cb", "value_changed_event")} for name, (action, predicate) in {**COMMON, **SPECIFIC.get(target, {})}.items()}


def offset_display_frame(frame: dict | None, dx: int, dy: int) -> dict | None:
    if not frame or (dx == 0 and dy == 0):
        return frame
    result = dict(frame)
    if "points" in result:
        result["points"] = [[x + dx, y + dy, *point[2:]] for point in result["points"] for x, y in [point[:2]]]
    if "box" in result:
        x0, y0, x1, y1 = result["box"]
        result["box"] = [x0 + dx, y0 + dy, x1 + dx, y1 + dy]
    if "center_x" in result:
        result["center_x"] += dx
    if "right_x" in result:
        result["right_x"] += dx
    return result


def build_display_program(method: str, case_id: str, canvas: bool = False,
                          width: int = 320, height: int = 240) -> str:
    display_width, display_height = width, height
    target = "M5.Display.Canvas" if canvas else "M5.Display"
    lines = [GUEST_COMMON % (case_id, target), "M5.Lcd.fillScreen(0x0B1014)"]
    canvas_origin = (0, 0)
    if canvas:
        width, height = min(280, width), min(200, height)
        if display_width == display_height:
            canvas_origin = ((display_width - width) // 2, (display_height - height) // 2)
        # Cardputer-ADV has no PSRAM. A failed createSprite can return a zero
        # sized Canvas without raising; admit its actual dimensions first.
        psram = width > 240
        lines += [f"obj=M5.Lcd.newCanvas({width},{height},16,{psram!r})", f"expected_width={width};expected_height={height}", "assert obj.width()==expected_width and obj.height()==expected_height,'canvas allocation failed'", "obj.fillScreen(0x0B1014)", "canvas_members=[]", "for canvas_name in sorted(dir(obj)):", "    if not canvas_name.startswith('_'):", "        canvas_value=getattr(obj,canvas_name)", "        canvas_members.append([canvas_name,str(type(canvas_value)),bool(callable(canvas_value))])", "print('M5EMU_API_UI_BEGIN Canvas')", "print('M5EMU_API_UI '+json.dumps({'kind':'members','path':'M5.Display.Canvas','members':canvas_members}))", "print('M5EMU_API_UI_END Canvas')"]
    else:
        lines += ["obj=M5.Lcd", f"expected_width={width};expected_height={height}"]
    lines += ["obj.setTextColor(0xF3F7F8,0x0B1014)", "obj.setFont(M5.Lcd.FONTS.DejaVu18)", "obj.drawString('API '+API_TARGET,8,8)"]
    if canvas:
        lines += [f"if not hasattr(obj,{method!r}):", f"    emit('RESULT',method={method!r},status='NOT_EXPORTED',reason='actual Canvas member absent on this firmware')", "    emit('READY',status='ACTUAL_EXPORT_UNAVAILABLE')", "    while True:", "        M5.update()", "        time.sleep_ms(20)"]
    recipe = display_recipe_for(method, width, height)
    if recipe is None:
        reason = DISPLAY_UNASSIGNED_REASONS.get(method, "No behavior-specific recipe yet")
        lines += ["emit('RESULT',method=" + repr(method) + ",status='NOT_RUN',reason=" + repr(reason) + ")"]
    else:
        action, predicate, frame = recipe
        if method in {"drawPng", "drawBmp", "drawImage", "drawJpg"}:
            extension = {"drawPng": "png", "drawBmp": "bmp", "drawImage": "png", "drawJpg": "jpg"}[method]
            lines += [
                f"_fixture_source=open(os.getcwd()+'/fixture.{extension}','rb')",
                "_fixture_data=_fixture_source.read()",
                "_fixture_source.close()",
                f"_fixture_target=open('/flash/api-sweep-fixture.{extension}','wb')",
                "_fixture_target.write(_fixture_data)",
                "_fixture_target.close()",
            ]
        frame = offset_display_frame(frame, *canvas_origin)
        if canvas and method == "push":
            action = action.replace("obj.push(0,0)", f"obj.push({canvas_origin[0]},{canvas_origin[1]})")
        lines += ["try:", "    " + action]
        if canvas and method != "push":
            lines += [f"    obj.push({canvas_origin[0]},{canvas_origin[1]})"]
        lines += ["    settle()"]
        if predicate:
            lines += ["    ok=bool(" + predicate + ")", "    emit('RESULT',method=" + repr(method) + ",status='STATE_PASS' if ok else 'FAIL',oracle=" + repr(predicate) + ")"]
        if frame:
            lines += ["    emit('FRAME_ORACLE',method=" + repr(method) + ",oracle=" + repr(frame) + ",tolerance=8)"]
        lines += ["except Exception as error:", "    emit('RESULT',method=" + repr(method) + ",status='FAIL',error=repr(error))"]
    lines += ["emit('READY',status='AWAITING_FRAME')", "while True:", "    M5.update()", "    time.sleep_ms(20)"]
    if canvas:
        allocation = next(index for index, line in enumerate(lines) if line.startswith("obj=M5.Lcd.newCanvas("))
        lines = lines[:allocation + 1] + ["try:"] + ["    " + line for line in lines[allocation + 1:]] + ["finally:", "    obj.delete()"]
    return "\n".join(lines) + "\n"


def widget_frame_recipe(target: str, method: str | None, width: int, height: int) -> dict | None:
    c = widget_coordinates(width, height)
    if target == "Title" and width == height:
        # Title draws a full-width top bar, while the StopWatch presents only
        # the inscribed circle. Its state methods remain testable, but a
        # rectangular top-strip frame oracle is not a valid visual claim.
        return None
    if target == "QRCode":
        return {"kind": "qr_decode", "text": "UPDATED-API" if method == "setText" else "UIFLOW2-API"}
    if method == "setVisible":
        # Verify disappearance across the actual object region, not just one
        # sample that could miss a still-visible glyph or line.
        boxes = {
            "Label": [c["sx"](20), c["sy"](60), min(width - 1, c["sx"](235)), min(height - 1, c["sy"](120))],
            "Title": [0, 0, width - 1, max(1, min(height - 1, c["sy"](20)))],
            "Image": [c["sx"](40), c["sy"](60), min(width - 1, c["sx"](40) + 32), min(height - 1, c["sy"](60) + 32)],
            "Line": [c["sx"](20), c["sy"](60), min(width - 1, c["sx"](221)), max(1, min(height - 1, c["sy"](145)))],
            "Circle": [max(0, c["sx"](120) - c["sr"](45)), max(0, c["sy"](100) - c["sr"](45)), min(width - 1, c["sx"](120) + c["sr"](46)), min(height - 1, c["sy"](100) + c["sr"](46))],
            "Rectangle": [c["sx"](20), c["sy"](60), min(width - 1, c["sx"](20) + c["sw"](160)), min(height - 1, c["sy"](60) + c["sh"](80))],
            "Triangle": [c["sx"](20), c["sy"](60), min(width - 1, c["sx"](220)), min(height - 1, c["sy"](140))],
        }
        box = boxes[target]
        return {"kind": "color_region", "rgb": 0x304850 if target == "Title" else 0x0B1014, "box": box, "minimum": (box[2]-box[0])*(box[3]-box[1])}
    if target in ("Label", "Title"):
        title = target == "Title"
        box = [0, 0, width - 1, max(1, min(height - 1, c["sy"](60)))] if title else [
            c["sx"](20), c["sy"](60), min(width - 1, c["sx"](300)),
            max(c["sy"](60) + 1, min(height - 1, c["sy"](130))),
        ]
        if method == "setColor":
            return {"kind": "color_region", "rgb": 0x38B8C8, "box": box, "minimum": 5}
        text = ("Updated title" if title else "Updated label") if method == "setText" else ("Widget title" if title else "Widget label")
        if method in (None, "setText", "setCursor", "setFont"):
            return {"kind": "text", "text": text, "box": box}
        return None
    if target == "Image":
        x, y = (c["sx"](80), c["sy"](100)) if method == "setCursor" else (c["sx"](40), c["sy"](60))
        offsets = (2,26) if method == "setScale" else (2,12)
        colors = [0xFFFF00,0x0000FF,0x00FF00,0xFF0000] if method == "setImage" else [0xFF0000,0x00FF00,0x0000FF,0xFFFF00]
        a, b = offsets
        return {"kind": "pixels", "points": [[x+a,y+a,colors[0]],[x+b,y+a,colors[1]],[x+a,y+b,colors[2]],[x+b,y+b,colors[3]]]}
    color = 0x58C78A if method == "setColor" else 0x38B8C8
    if target == "Circle":
        point = [c["sx"](160), c["sy"](120)] if method == "setCursor" else [c["sx"](120) + c["sr"](50), c["sy"](100)] if method == "setRadius" else [c["sx"](120), c["sy"](100)]
    elif target == "Rectangle":
        point = [c["sx"](100), c["sy"](110)] if method == "setCursor" else [c["sx"](80), c["sy"](100)]
    elif target == "Triangle":
        point = [c["sx"](140), c["sy"](100)] if method == "setPoints" else [c["sx"](120), c["sy"](100)]
    elif target == "Line":
        point = [c["sx"](120), c["sy"](100)]
    else:
        return None
    return {"kind": "pixels", "points": [point+[color]]}


def build_widgets_program(target: str, method: str | None, case_id: str, width: int = 320, height: int = 240) -> str:
    if target not in WIDGET_CONSTRUCTORS:
        raise ValueError(f"Unknown native widget {target}")
    constructor = widget_constructor(target, width, height)
    lines = [GUEST_COMMON % (case_id, "M5.Widgets." + target), "Widgets.fillScreen(0x0B1014)", "obj=" + constructor, "settle()", "emit('CONSTRUCTED',status='PENDING_FRAME',class_name=" + repr(target) + ")"]
    if method:
        action = WIDGET_RECIPES[target].get(method)
        if action is None:
            lines += ["emit('RESULT',method=" + repr(method) + ",status='NOT_RUN',reason='No behavior-specific recipe yet')"]
        else:
            action = adapt_widget_action(target, method, action, width, height)
            lines += ["try:", "    " + action, "    settle()", "    emit('RESULT',method=" + repr(method) + ",status='PENDING_FRAME',action=" + repr(action) + ")", "except Exception as error:", "    emit('RESULT',method=" + repr(method) + ",status='FAIL',error=repr(error))"]
    oracle = widget_frame_recipe(target, method, width, height)
    if oracle is not None and not (target == "QRCode" and method == "setVisible"):
        lines += ["emit('FRAME_ORACLE',method=" + repr(method or target) + ",oracle=" + repr(oracle) + ",tolerance=8)"]
    lines += ["emit('READY',status='AWAITING_FRAME')", "while True:", "    M5.update()", "    time.sleep_ms(20)"]
    return "\n".join(lines) + "\n"


def build_lifecycle_program(case_id: str = "m5ui-lifecycle") -> str:
    lines = [GUEST_COMMON % (case_id, "m5ui.lifecycle"), "import m5ui", "import m5ui.port as port", "import lvgl as lv"]
    for cycle in range(2):
        lines += ["m5ui.init()", "assert lv.is_initialized()", "loop=port.event_loop._instance", "assert loop is not None and loop._initialized", "page=m5ui.M5Page(bg_c=0x0B1014)", "label=m5ui.M5Label('Lifecycle '+str(" + str(cycle) + "),x=20,y=80,text_c=0xF3F7F8,parent=page)", "page.screen_load()", "settle()", "emit('RESULT',method='init',cycle=" + str(cycle) + ",status='STATE_PASS',oracle='native LVGL and real event_loop initialized')", "m5ui.deinit()", "assert not lv.is_initialized()", "assert port.event_loop._instance is None", "emit('RESULT',method='deinit',cycle=" + str(cycle) + ",status='STATE_PASS',oracle='native LVGL and real event_loop deinitialized')"]
    lines += ["m5ui.init()", "page=m5ui.M5Page(bg_c=0x0B1014)", "label=m5ui.M5Label('Lifecycle restored',x=20,y=80,text_c=0xF3F7F8,parent=page)", "page.screen_load()", "settle()", "emit('READY',status='AWAITING_FRAME')", "try:", "    while True:", "        M5.update()", "        time.sleep_ms(20)", "finally:", "    m5ui.deinit()"]
    return "\n".join(lines) + "\n"


def build_widgets_module_program(method: str, case_id: str, width: int = 320, height: int = 240) -> str:
    lines = [GUEST_COMMON % (case_id, "M5.Widgets"), "Widgets.fillScreen(0x0B1014)"]
    if method == "setBrightness":
        lines += ["Widgets.setBrightness(192)", "assert M5.Lcd.getBrightness()==192", "emit('RESULT',method='setBrightness',status='STATE_PASS',oracle='native display brightness readback')"]
    elif method == "setRotation":
        lines += ["Widgets.setRotation(1)", f"assert M5.Lcd.getRotation()==1 and M5.Lcd.width()=={height} and M5.Lcd.height()=={width}", "emit('RESULT',method='setRotation',status='STATE_PASS',oracle='native display rotation and swapped dimensions readback')"]
    elif method == "fillScreen":
        frame = display_recipe_for("fillScreen", width, height)[2]
        lines += ["Widgets.fillScreen(0x38B8C8)", "emit('FRAME_ORACLE',method='fillScreen',oracle=" + repr(frame) + ",tolerance=8)"]
    else:
        raise ValueError("Unknown Widgets module method " + method)
    lines += ["settle()", "emit('READY',status='AWAITING_FRAME')", "while True:", "    M5.update()", "    time.sleep_ms(20)"]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", choices=("m5ui", "display", "canvas", "widgets", "widgets-module", "lifecycle", "native-styles"), default="m5ui")
    parser.add_argument("--uiflow-root", type=Path)
    parser.add_argument("--target", required=True)
    parser.add_argument("--method", action="append", default=[])
    parser.add_argument("--case-id", default="ui-api")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.lane == "m5ui":
        source = build_m5ui_program(args.target, args.method, args.case_id)
    elif args.lane == "widgets":
        source = build_widgets_program(args.target, args.method[0] if args.method else None, args.case_id)
    elif args.lane == "widgets-module":
        if len(args.method) != 1:
            parser.error("widgets-module uses exactly one --method")
        source = build_widgets_module_program(args.method[0], args.case_id)
    elif args.lane == "lifecycle":
        source = build_lifecycle_program(args.case_id)
    elif args.lane == "native-styles":
        if args.uiflow_root is None:
            parser.error("native-styles needs --uiflow-root for authoritative style argument types")
        source = build_native_style_program(args.uiflow_root, args.case_id)
    else:
        if len(args.method) != 1:
            parser.error("display and canvas use exactly one --method so each fresh frame belongs to one oracle")
        source = build_display_program(args.method[0], args.case_id, canvas=args.lane == "canvas")
    args.output.write_text(source, encoding="utf-8")
    print(json.dumps({"output": str(args.output), "target": args.target, "requested_methods": args.method, "lane": args.lane}))


if __name__ == "__main__":
    main()
