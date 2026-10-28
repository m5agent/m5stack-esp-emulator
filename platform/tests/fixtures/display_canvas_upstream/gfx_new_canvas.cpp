mp_obj_t gfx_newCanvas(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    enum {ARG_w, ARG_h, ARG_bpp, ARG_psram};
    /* *FORMAT-OFF* */
    const mp_arg_t allowed_args[] = {
        { MP_QSTR_w,     MP_ARG_INT | MP_ARG_REQUIRED, {.u_int = 0 } },
        { MP_QSTR_h,     MP_ARG_INT | MP_ARG_REQUIRED, {.u_int = 0 } },
        { MP_QSTR_bpp,   MP_ARG_INT                  , {.u_int = -1 } },
        { MP_QSTR_psram, MP_ARG_BOOL                 , {.u_bool = false } },
    };
    /* *FORMAT-ON* */
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    // The first parameter is the GFX object, parse from second parameter.
    mp_arg_parse_all(n_args - 1, pos_args + 1, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    auto gfx = getGfx(&pos_args[0]);
    auto canvas = new M5Canvas(gfx);
    canvas->setPsram((bool)args[ARG_psram].u_bool);
    if (args[ARG_bpp].u_int != -1) {
        canvas->setColorDepth(args[ARG_bpp].u_int);
    }
    canvas->createSprite(args[ARG_w].u_int, args[ARG_h].u_int);
    gfx_obj_t *res = mp_obj_malloc_with_finaliser(gfx_obj_t, &mp_gfxcanvas_type);
    res->base.type = &mp_gfxcanvas_type;
    res->gfx = canvas;
    return MP_OBJ_FROM_PTR(res);
}

