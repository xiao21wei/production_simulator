cmake_minimum_required(VERSION 3.16)
project(InfluenceAwareConstruct LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_executable(influence_aware_scheduler
    src/main.cpp
    src/ConstructionApi.cpp
    src/DataProc.cpp
    src/Experiment.cpp
    src/GreedySearch.cpp
    src/Job.cpp
    src/Machine.cpp
    src/Order.cpp
    src/RandomSearch.cpp
    src/Schedule.cpp
    src/TabuSearch.cpp
)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(influence_aware_scheduler PRIVATE
        -O2
    )
endif()
