ENTRY(_start)
MEMORY {
  iram (rwx) : ORIGIN = 0x40080000, LENGTH = 0x1F000
}
SECTIONS {
  .text : {
    *(.literal .literal.*)
    *(.text .text.*)
    *(.rodata .rodata.*)
  } > iram
  .data : { *(.data .data.*) } > iram
  .bss : { *(.bss .bss.*) *(COMMON) } > iram
}
