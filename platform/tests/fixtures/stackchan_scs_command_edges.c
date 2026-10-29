/* Controller-only regression for the official SCSCL command sequences.
 * Included after the packet helpers in test_stackchan_scs_patch.py.
 * No PWM mechanics or speed-to-time conversion is assumed here. */
#ifndef SCS_COMMAND_EDGES_CASE
#define SCS_COMMAND_EDGES_CASE 0
#endif

static void scs_repeat_torque_cases(void)
{
    /* WRITE, REG_WRITE/ACTION and SYNC_WRITE share the same edge rule. */
    for (int path = 0; path < 3; path++) {
        fresh();power(true);torque(1,1);move(1,3,1000,1000);
        now_ms=400;assert(read_position(1)==676);
        if (path==0) {
            torque(1,1);
        } else if (path==1) {
            uint8_t one=1;write_bytes(1,4,40,&one,1);
            packet(0xfe,5,NULL,0,true);
        } else {
            uint8_t sync[]={40,1,1,1};
            packet(0xfe,0x83,sync,sizeof(sync),true);
        }
        now_ms=1000;assert(read_position(1)==1000);
        assert(scs_peer->mem[1][66]==0);
    }
    /* Real off/lock edges freeze feedback; re-enabling starts the held goal. */
    for (int stopped=0; stopped<=2; stopped+=2) {
        fresh();power(true);torque(1,1);move(1,3,1000,1000);
        now_ms=400;torque(1,stopped);assert(read_position(1)==676);
        now_ms=1000;torque(1,stopped);assert(read_position(1)==676);
        assert(scs_peer->mem[1][66]==0);
        torque(1,1);now_ms=1500;assert(read_position(1)==838);
        now_ms=2000;assert(read_position(1)==1000);
    }
}

static void scs_explicit_command_cases(void)
{
    /* An explicitly reissued position/time/speed command restarts, even if
     * bytes are unchanged. A torque-only repeat must not suppress this. */
    for (int path=0; path<6; path++) {
        fresh();power(true);torque(1,1);move(1,3,1000,1000);
        now_ms=400;assert(read_position(1)==676);
        if (path<3) {
            uint8_t value[]={path==2?0:3,path==2?0:232};
            write_bytes(1,3,42+path*2,value,sizeof(value));
        } else if (path==3) {
            move(1,3,1000,1000);
        } else if (path==4) {
            move(1,4,1000,1000);packet(0xfe,5,NULL,0,true);
        } else {
            uint8_t sync[]={42,6,1,3,232,3,232,0,0};
            packet(0xfe,0x83,sync,sizeof(sync),true);
        }
        now_ms=1000;assert(read_position(1)==870);
        assert(scs_peer->mem[1][66]==1);
        now_ms=1400;assert(read_position(1)==1000);
    }
    /* EEPROM, LOCK and the reserved byte next to torque are not commands. */
    for (int path=0; path<4; path++) {
        fresh();power(true);torque(1,1);move(1,3,1000,1000);now_ms=400;
        if (path==0) {
            uint8_t min[]={0,100};write_bytes(1,3,9,min,sizeof(min));
        } else if (path==1) {
            uint8_t lock=1;write_bytes(1,3,48,&lock,1);
        } else if (path==2) {
            uint8_t reserved=0;write_bytes(1,3,41,&reserved,1);
        } else {
            uint8_t min[]={0,100};write_bytes(1,4,9,min,sizeof(min));
            uint8_t lock=1;write_bytes(1,4,48,&lock,1);
            packet(0xfe,5,NULL,0,true);
        }
        now_ms=1000;assert(read_position(1)==1000);
        assert(scs_peer->mem[1][66]==0);
    }
}

static void scs_mode_restore_cases(void)
{
    fresh();power(true);torque(1,1);
    uint8_t limits[]={0,100,3,132};write_bytes(1,3,9,limits,sizeof(limits));
    assert(uart.rx_len==6);
    /* SCSCL::SwitchMode(1), followed by WritePWM(-512). */
    uint8_t pwm_mode[]={0,0,0,0};write_bytes(1,3,9,pwm_mode,sizeof(pwm_mode));
    uint8_t pwm[]={6,0};write_bytes(1,3,44,pwm,sizeof(pwm));
    now_ms=1000;assert(read_position(1)==460);
    /* Official SwitchMode(0) writes cached min first, then cached max.
     * Its temporary min>max interval must ACK but cannot drive the shaft. */
    uint8_t min[]={0,100};write_bytes(1,3,9,min,sizeof(min));
    assert(uart.rx_len==6);
    assert(scs_get_be16(scs_peer->mem[1],9)==100);
    assert(scs_get_be16(scs_peer->mem[1],11)==0);
    move(1,3,800,100);now_ms+=1000;
    assert(read_position(1)==460&&scs_peer->mem[1][66]==0);
    uint8_t max[]={3,132};write_bytes(1,3,11,max,sizeof(max));
    assert(uart.rx_len==6&&!scs_pwm_mode(scs_peer->mem[1]));
    move(1,3,800,100);now_ms+=50;assert(read_position(1)==630);
    now_ms+=50;assert(read_position(1)==800);
    /* Both raw bounds remain valid, and position commands use the final
     * configured limits rather than the temporary restoration interval. */
    move(1,3,0,100);now_ms+=100;assert(read_position(1)==100);
    move(1,3,1000,100);now_ms+=100;assert(read_position(1)==900);
    uint8_t invalid[]={3,233};
    write_bytes(1,3,9,invalid,sizeof(invalid));assert(uart.rx_len==0);
    assert(scs_get_be16(scs_peer->mem[1],9)==100);
    write_bytes(1,3,11,invalid,sizeof(invalid));assert(uart.rx_len==0);
    assert(scs_get_be16(scs_peer->mem[1],11)==900);
    write_bytes(1,3,42,invalid,sizeof(invalid));assert(uart.rx_len==0);
    assert(scs_get_be16(scs_peer->mem[1],42)==900);
    uint8_t invalid_torque=3;write_bytes(1,3,40,&invalid_torque,1);
    assert(uart.rx_len==0&&scs_peer->mem[1][40]==1);
}

static void scs_observer_deadline_cases(void)
{
    fresh();power(true);torque(1,1);move(1,3,1000,1000);
    uint8_t command[56];memcpy(command,scs_peer->mem[1],sizeof(command));
    now_ms=250;
    for(int i=0;i<5;i++) {
        QObject *state=snapshot();QObject *servos=field(state,"servos");
        assert(field(servos->value[0],"present_position")->number==595);
        assert(!memcmp(command,scs_peer->mem[1],sizeof(command)));
    }
    now_ms=400;snapshot();assert(present(1)==676);
    now_ms=1000;snapshot();assert(present(1)==1000);
    assert(scs_peer->mem[1][66]==0);
    assert(!memcmp(command,scs_peer->mem[1],sizeof(command)));
}

static void scs_command_edges_cases(void)
{
    if (SCS_COMMAND_EDGES_CASE==0||SCS_COMMAND_EDGES_CASE==1) {
        scs_repeat_torque_cases();
    }
    if (SCS_COMMAND_EDGES_CASE==0||SCS_COMMAND_EDGES_CASE==2) {
        scs_mode_restore_cases();
    }
    if (SCS_COMMAND_EDGES_CASE==0) {
        scs_explicit_command_cases();
        scs_observer_deadline_cases();
    }
}
