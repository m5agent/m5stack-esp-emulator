// Standalone WASM32 ABI comparison; not a QEMU/firmware performance claim.
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <setjmp.h>
#include <ffi.h>
#include <emscripten.h>
#define QEMU_DISABLE_CFI __attribute__((no_sanitize("cfi-icall")))
#include "tci-wasm-call.h"
_Static_assert(sizeof(void*) == 4, "wasm32 only");
_Static_assert(sizeof(ffi_arg) == 4, "32-bit libffi result word required");
static volatile uint32_t calls, observed;
static uint32_t mix(uint32_t x, uint32_t v) { return (x ^ v) * 16777619u + (v >> 19); }
static __attribute__((noinline)) uint32_t r0(void){uint32_t x=0x811c9dc5u; calls++;return x;}
static __attribute__((noinline)) void v0(void){uint32_t x=0x811c9dc5u; calls++;observed=x;}
static __attribute__((noinline)) uint32_t r1(uint32_t a0){uint32_t x=0x811c9dc5u; x=mix(x,a0);calls++;return x;}
static __attribute__((noinline)) void v1(uint32_t a0){uint32_t x=0x811c9dc5u; x=mix(x,a0);calls++;observed=x;}
static __attribute__((noinline)) uint32_t r2(uint32_t a0, uint32_t a1){uint32_t x=0x811c9dc5u; x=mix(x,a0);x=mix(x,a1);calls++;return x;}
static __attribute__((noinline)) void v2(uint32_t a0, uint32_t a1){uint32_t x=0x811c9dc5u; x=mix(x,a0);x=mix(x,a1);calls++;observed=x;}
static __attribute__((noinline)) uint32_t r3(uint32_t a0, uint32_t a1, uint32_t a2){uint32_t x=0x811c9dc5u; x=mix(x,a0);x=mix(x,a1);x=mix(x,a2);calls++;return x;}
static __attribute__((noinline)) void v3(uint32_t a0, uint32_t a1, uint32_t a2){uint32_t x=0x811c9dc5u; x=mix(x,a0);x=mix(x,a1);x=mix(x,a2);calls++;observed=x;}
static __attribute__((noinline)) uint32_t r4(uint32_t a0, uint32_t a1, uint32_t a2, uint32_t a3){uint32_t x=0x811c9dc5u; x=mix(x,a0);x=mix(x,a1);x=mix(x,a2);x=mix(x,a3);calls++;return x;}
static __attribute__((noinline)) void v4(uint32_t a0, uint32_t a1, uint32_t a2, uint32_t a3){uint32_t x=0x811c9dc5u; x=mix(x,a0);x=mix(x,a1);x=mix(x,a2);x=mix(x,a3);calls++;observed=x;}
static __attribute__((noinline)) uint32_t r5(uint32_t a0, uint32_t a1, uint32_t a2, uint32_t a3, uint32_t a4){uint32_t x=0x811c9dc5u; x=mix(x,a0);x=mix(x,a1);x=mix(x,a2);x=mix(x,a3);x=mix(x,a4);calls++;return x;}
static __attribute__((noinline)) void v5(uint32_t a0, uint32_t a1, uint32_t a2, uint32_t a3, uint32_t a4){uint32_t x=0x811c9dc5u; x=mix(x,a0);x=mix(x,a1);x=mix(x,a2);x=mix(x,a3);x=mix(x,a4);calls++;observed=x;}
static __attribute__((noinline)) uint32_t r6(uint32_t a0, uint32_t a1, uint32_t a2, uint32_t a3, uint32_t a4, uint32_t a5){uint32_t x=0x811c9dc5u; x=mix(x,a0);x=mix(x,a1);x=mix(x,a2);x=mix(x,a3);x=mix(x,a4);x=mix(x,a5);calls++;return x;}
static __attribute__((noinline)) void v6(uint32_t a0, uint32_t a1, uint32_t a2, uint32_t a3, uint32_t a4, uint32_t a5){uint32_t x=0x811c9dc5u; x=mix(x,a0);x=mix(x,a1);x=mix(x,a2);x=mix(x,a3);x=mix(x,a4);x=mix(x,a5);calls++;observed=x;}
static __attribute__((noinline)) uint32_t r7(uint32_t a0, uint32_t a1, uint32_t a2, uint32_t a3, uint32_t a4, uint32_t a5, uint32_t a6){uint32_t x=0x811c9dc5u; x=mix(x,a0);x=mix(x,a1);x=mix(x,a2);x=mix(x,a3);x=mix(x,a4);x=mix(x,a5);x=mix(x,a6);calls++;return x;}
static __attribute__((noinline)) void v7(uint32_t a0, uint32_t a1, uint32_t a2, uint32_t a3, uint32_t a4, uint32_t a5, uint32_t a6){uint32_t x=0x811c9dc5u; x=mix(x,a0);x=mix(x,a1);x=mix(x,a2);x=mix(x,a3);x=mix(x,a4);x=mix(x,a5);x=mix(x,a6);calls++;observed=x;}
static void *rfns[]={(void*)r0,(void*)r1,(void*)r2,(void*)r3,(void*)r4,(void*)r5,(void*)r6,(void*)r7};
static void *vfns[]={(void*)v0,(void*)v1,(void*)v2,(void*)v3,(void*)v4,(void*)v5,(void*)v6,(void*)v7};
static __attribute__((noinline)) int32_t signed_pointer(int32_t a, uint32_t b, void *p) {
 calls++; return (int32_t)((uint32_t)a ^ b ^ (uintptr_t)p);
}
static __attribute__((noinline)) void *pointer_result(void *p) {calls++;return p;}
static __attribute__((noinline)) void forbidden(void) {calls++;}
static jmp_buf jump;
static __attribute__((noinline)) void jumping(uint32_t value) {calls++;longjmp(jump,(int)value);}
static void compare(ffi_cif *cif, void *fn, void **values, unsigned *cases) {
 uint8_t fast[16], normal[16];memset(fast,0xa5,sizeof fast);memset(normal,0xa5,sizeof normal);
 uint32_t before=calls;assert(m5_wasm_tci_call(cif,fn,fast,values));assert(calls==before+1);uint32_t out=observed;
 ffi_call(cif,(void(*)(void))fn,normal,values);assert(calls==before+2);assert(observed==out);
 assert(memcmp(fast,normal,sizeof fast)==0);(*cases)++;
}
static void rejected(ffi_cif *cif, void **values, unsigned *cases) {
 uint8_t result[16];memset(result,0xa5,sizeof result);uint32_t before=calls;
 assert(!m5_wasm_tci_call(cif,(void*)forbidden,result,values));assert(calls==before);
 for(unsigned i=0;i<sizeof result;i++)assert(result[i]==0xa5);(*cases)++;
}
int main(void) {
 unsigned accepted=0,rejections=0;ffi_cif cif;
 uint64_t slots[8];void *values[8];ffi_type *types[8];
 for(unsigned i=0;i<8;i++){values[i]=&slots[i];types[i]=&ffi_type_uint32;}
 for(unsigned n=0;n<=7;n++)for(unsigned variant=0;variant<4;variant++) {
  for(unsigned i=0;i<8;i++)slots[i]=0xa5a5a5a500000000ull|((0x80000001u+0x7f123u*i)^(variant*0x5a5a5a5au));
  for(unsigned i=0;i<n;i++)types[i]=(i%3==0?&ffi_type_uint32:i%3==1?&ffi_type_sint32:&ffi_type_pointer);
  assert(ffi_prep_cif(&cif,FFI_DEFAULT_ABI,n,&ffi_type_uint32,types)==FFI_OK);compare(&cif,rfns[n],values,&accepted);
  assert(ffi_prep_cif(&cif,FFI_DEFAULT_ABI,n,&ffi_type_void,types)==FFI_OK);compare(&cif,vfns[n],values,&accepted);
 }
 ffi_type *signed_types[]={&ffi_type_sint32,&ffi_type_uint32,&ffi_type_pointer};
 slots[0]=0xffffffffu;slots[1]=0x80000000u;slots[2]=0xf0123456u;
 assert(ffi_prep_cif(&cif,FFI_DEFAULT_ABI,3,&ffi_type_sint32,signed_types)==FFI_OK);compare(&cif,(void*)signed_pointer,values,&accepted);
 assert(ffi_prep_cif(&cif,FFI_DEFAULT_ABI,1,&ffi_type_pointer,&signed_types[2])==FFI_OK);compare(&cif,(void*)pointer_result,&values[2],&accepted);
 ffi_type *unsupported[]={&ffi_type_uint64,&ffi_type_double};
 for(unsigned i=0;i<2;i++) {assert(ffi_prep_cif(&cif,FFI_DEFAULT_ABI,1,&ffi_type_void,&unsupported[i])==FFI_OK);rejected(&cif,values,&rejections);}
 ffi_type *elements[]={&ffi_type_uint32,&ffi_type_uint32,NULL};ffi_type structure={.size=0,.alignment=0,.type=FFI_TYPE_STRUCT,.elements=elements};ffi_type *struct_args[]={&structure};
 assert(ffi_prep_cif(&cif,FFI_DEFAULT_ABI,1,&ffi_type_void,struct_args)==FFI_OK);rejected(&cif,values,&rejections);
 assert(ffi_prep_cif(&cif,FFI_DEFAULT_ABI,0,&ffi_type_uint64,NULL)==FFI_OK);rejected(&cif,values,&rejections);
 assert(ffi_prep_cif(&cif,FFI_DEFAULT_ABI,0,&ffi_type_double,NULL)==FFI_OK);rejected(&cif,values,&rejections);
 assert(ffi_prep_cif(&cif,FFI_DEFAULT_ABI,0,&structure,NULL)==FFI_OK);rejected(&cif,values,&rejections);
 for(unsigned i=0;i<8;i++)types[i]=&ffi_type_uint32;
 assert(ffi_prep_cif(&cif,FFI_DEFAULT_ABI,8,&ffi_type_void,types)==FFI_OK);rejected(&cif,values,&rejections);
 assert(ffi_prep_cif_var(&cif,FFI_DEFAULT_ABI,1,2,&ffi_type_void,types)==FFI_OK);rejected(&cif,values,&rejections);
 assert(ffi_prep_cif(&cif,FFI_DEFAULT_ABI,1,&ffi_type_void,types)==FFI_OK);cif.abi=FFI_FIRST_ABI;rejected(&cif,values,&rejections);
 assert(ffi_prep_cif(&cif,FFI_DEFAULT_ABI,1,&ffi_type_void,types)==FFI_OK);
 volatile int jump_fast=0,jump_ffi=0;slots[0]=37;
 int code=setjmp(jump);if(code==0){m5_wasm_tci_call(&cif,(void*)jumping,NULL,values);assert(0);}else{assert(code==37);jump_fast=code;}
 code=setjmp(jump);if(code==0){ffi_call(&cif,(void(*)(void))jumping,NULL,values);assert(0);}else{assert(code==37);jump_ffi=code;}
 assert(jump_fast==37&&jump_ffi==37);
 printf("{\"status\":\"PASS\",\"accepted_cases\":%u,\"rejected_without_call\":%u,\"setjmp_fast\":%d,\"setjmp_ffi\":%d,\"microbenchmark\":false}\n",accepted,rejections,jump_fast,jump_ffi);
 return 0;
}
