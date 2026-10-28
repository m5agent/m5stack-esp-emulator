// -------- M5Widgets QRCode
typedef struct _widgets_qrcode_obj_t {
    mp_obj_base_t base;
    LGFX_Device *gfx;
    const char *text;
    widgets_pos_t pos;
    widgets_size_t size;
    uint8_t version;
}widgets_qrcode_obj_t;

static void m5widgets_qrcode_erase_helper(const widgets_qrcode_obj_t *self) {
    self->gfx->fillRect(self->pos.x0, self->pos.y0, self->size.w, self->size.w, _bg_color_g);
}

static void m5widgets_qrcode_draw_helper(const widgets_qrcode_obj_t *self) {
    uint32_t stash_color = self->gfx->getRawColor();
    self->gfx->qrcode(self->text, self->pos.x0, self->pos.y0, self->size.w, self->version);
    self->gfx->setRawColor(stash_color);
}

mp_obj_t m5widgets_qrcode_setText(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    enum {ARG_text};
    /* *FORMAT-OFF* */
    const mp_arg_t allowed_args[] = {
        { MP_QSTR_text, MP_ARG_OBJ | MP_ARG_REQUIRED, {.u_obj = mp_const_none } }
    };
    /* *FORMAT-ON* */
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args - 1, pos_args + 1, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    widgets_qrcode_obj_t *self = (widgets_qrcode_obj_t *)pos_args[0];

    const char *new_text = mp_obj_str_get_str(args[ARG_text].u_obj);
    if (strcmp(self->text, new_text) == 0) {
        return mp_const_none;
    }
    m5widgets_qrcode_draw_helper(self);
    return mp_const_none;
}

mp_obj_t m5widgets_qrcode_setSize(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    enum {ARG_w};
    /* *FORMAT-OFF* */
    const mp_arg_t allowed_args[] = {
        { MP_QSTR_w, MP_ARG_INT | MP_ARG_REQUIRED, {.u_int = 0 } }
    };
    /* *FORMAT-ON* */
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args - 1, pos_args + 1, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    widgets_qrcode_obj_t *self = (widgets_qrcode_obj_t *)pos_args[0];
    self->size.w = args[ARG_w].u_int;
    m5widgets_qrcode_draw_helper(self);
    return mp_const_none;
}

mp_obj_t m5widgets_qrcode_setVersion(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    enum {ARG_version};
    /* *FORMAT-OFF* */
    const mp_arg_t allowed_args[] = {
        { MP_QSTR_version, MP_ARG_INT | MP_ARG_REQUIRED, {.u_int = 0 } }
    };
    /* *FORMAT-ON* */
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args - 1, pos_args + 1, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    widgets_qrcode_obj_t *self = (widgets_qrcode_obj_t *)pos_args[0];
    self->version = args[ARG_version].u_int;
    m5widgets_qrcode_draw_helper(self);
    return mp_const_none;
}

mp_obj_t m5widgets_qrcode_setCursor(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    enum {ARG_x, ARG_y};
    /* *FORMAT-OFF* */
    const mp_arg_t allowed_args[] = {
        { MP_QSTR_x, MP_ARG_INT | MP_ARG_REQUIRED, {.u_int = 0 } },
        { MP_QSTR_y, MP_ARG_INT | MP_ARG_REQUIRED, {.u_int = 0 } }
    };
    /* *FORMAT-ON* */
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args - 1, pos_args + 1, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    widgets_qrcode_obj_t *self = (widgets_qrcode_obj_t *)pos_args[0];
    self->pos.x0 = args[ARG_x].u_int;
    self->pos.y0 = args[ARG_y].u_int;
    m5widgets_qrcode_draw_helper(self);
    return mp_const_none;
}

