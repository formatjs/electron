// SPDX-License-Identifier: MIT
.section .note.electron_node,"a",@note
.balign 4
.globl node_dependency_note
.type node_dependency_note,@object
node_dependency_note:
  .long .Lname_end - .Lname
  .long .Ldata_end - .Ldata
  .long 0x2f01
.Lname:
  .asciz "electron-node-fixture"
.Lname_end:
.balign 4
.Ldata:
  .ascii "declared resource bytes"
.Ldata_end:
.balign 4
.size node_dependency_note, .-node_dependency_note
.section .note.GNU-stack,"",@progbits
