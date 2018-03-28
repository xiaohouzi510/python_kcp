#!/bin/bash

NUM=`ps x | grep "python.*py" | grep -v grep | wc -l`;

if [[ $NUM -gt 0 ]];
then
    ps x | grep "python.*py" | grep -v grep | awk ' { print $1; }' | xargs kill -9;
    echo "kill robot success";
else
    echo "not robot run";
fi

