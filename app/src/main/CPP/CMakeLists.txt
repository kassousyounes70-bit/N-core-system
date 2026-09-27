cmake_minimum_required(VERSION 3.22.1)

project(protector LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(protector SHARED native_crypto.cpp)

find_library(log-lib log)
target_link_libraries(protector ${log-lib})
