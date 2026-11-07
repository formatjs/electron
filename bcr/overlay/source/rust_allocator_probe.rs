// SPDX-License-Identifier: MIT
#[no_mangle]
pub extern "C" fn electron_rust_allocate_pattern() -> *mut u8 {
    let bytes = vec![0x6bu8; 256].into_boxed_slice();
    Box::into_raw(bytes) as *mut u8
}

#[no_mangle]
pub unsafe extern "C" fn electron_rust_free_pattern(pointer: *mut u8) {
    if !pointer.is_null() {
        let bytes = std::ptr::slice_from_raw_parts_mut(pointer, 256);
        unsafe { drop(Box::from_raw(bytes)); }
    }
}

#[no_mangle]
pub extern "C" fn electron_rust_fallible_reserve() -> bool {
    let mut bytes = Vec::<u8>::new();
    bytes.try_reserve_exact(isize::MAX as usize / 2).is_err()
}
