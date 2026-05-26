# == DO NOT EDIT THE FOLLOWING LINES for the Raspberry Pi Pico VS Code Extension to work ==
if(WIN32)
    set(USERHOME $ENV{USERPROFILE})
else()
    set(USERHOME $ENV{HOME})
endif()
set(sdkVersion 2.2.0)
set(toolchainVersion RISCV_ZCB_RPI_2_2_0_3)
set(picotoolVersion 2.2.0-a4)
set(picoVscode ${USERHOME}/.pico-sdk/cmake/pico-vscode.cmake)
if (EXISTS ${picoVscode})
    include(${picoVscode})
endif()
# ====================================================================================
cmake_minimum_required(VERSION 3.13)

# Copy pico_sdk_import.cmake from your SDK:
#   $PICO_SDK_PATH/external/pico_sdk_import.cmake
include(pico_sdk_import.cmake)

project(solvakt C CXX ASM)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(PICO_BOARD pico2 CACHE STRING "Board type")

pico_sdk_init()

add_executable(solvakt main.c)

target_link_libraries(solvakt
    pico_stdlib
    hardware_uart
    hardware_watchdog
)

pico_enable_stdio_usb(solvakt 1)
pico_enable_stdio_uart(solvakt 0)

pico_add_extra_outputs(solvakt)
