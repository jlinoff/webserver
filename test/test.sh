#!/bin/bash
#
# This is not a complete test because it doesn't check the browser output.
# That must be done manually.
#

# ================================================================
# Functions
# ================================================================
function banner() {
    local Title="$*"
    printf '\n'
    printf '# ================================================================ #\n'
    printf '# %-64s #\n' "$Title"
    printf '# ================================================================ #\n'
}

function test_banner() {
    local Title=$(printf 'Test %03d' $1)
    banner "$Title"
}

function test_passed() {
    printf 'Test: Passed - test %03d\n' $1
    (( Passed++ ))
    (( Total++ ))
}

function test_failed() {
    printf 'Test: Failed - test %03d - %s\n' $1 "$2"
    (( Failed++ ))
    (( Total++ ))
    local ftid=$(printf '%03d' "$1")
    FailedIds=(${FailedIds[@]} $ftid)
}

function kill_webserver() {
    local Port=$1
    echo "Killing webserver running on port $Port."

    # First try SIGINT (2) -- same keyboard interrupt
    Pids=($(ps auxww | grep $RootProg | grep 'testid=test0' | grep "port $Port" | grep -v grep | awk '{print $2;}'))
    if (( ${#Pids[@]} > 0 )) ; then
        echo kill -2 ${Pids[@]}
        kill -2 ${Pids[@]}
    fi

    # If SIGINT failed, nuke it.
    Pids=($(ps auxww | grep $RootProg | grep 'testid=test0' | grep "port $Port" | grep -v grep | awk '{print $2;}'))
    if (( ${#Pids[@]} > 0 )) ; then
        echo kill -9 ${Pids[@]}
        kill -9 ${Pids[@]}
    fi
    sleep 1
}

# ================================================================
# Main
# ================================================================
# Setup.
TestDir=$(pwd)
RootDir=$(cd $TestDir/.. && pwd)
RootProg=webserver.py
Webserver=$RootDir/$RootProg
Passed=0
Failed=0
Total=0
tid=0
PortBase=9200
FailedId=()

if [ ! -f $Webserver ] ; then
    echo "ERROR: $Webserver not found."
    exit 1
fi

wget -h >/dev/null
if (( $? )) ; then
    echo "ERROR: wget not available."
    exit 1
fi

# ================================================================
# Test 001 - initial page test
# ================================================================
(( tid++ ))
tids=$(printf 'test%03d' $tid)
test_banner $tid
Port=$(( $PortBase + $tid ))
kill_webserver $Port
set -x
$Webserver --extra "testid=$tids" --port $Port --webdir $RootDir/www -L debug &
st=$?
set +x
if (( $st )) ; then
    test_failed $tid "webserver"
else
    sleep 1
    set -x
    wget http://localhost:$Port -O $tids.out
    st=$?
    set +x
    if (( $st )) ; then
        test_failed $tid "wget"
    else
        diff $tids.out $tids.ok >$tids.diff 2>&1
        if (( $? )) ; then
            test_failed $tid "diff"
        else
            test_passed $tid
            rm -f $tids.out $tids.diff
        fi
    fi
fi

# ================================================================
# Test 002 - directory test
# ================================================================
(( tid++ ))
tids=$(printf 'test%03d' $tid)
test_banner $tid
set -x
wget http://localhost:$Port/@ -O $tids.out
st=$?
set +x
if (( $st )) ; then
    test_failed $tid "wget"
else
    diff $tids.out $tids.ok >$tids.diff 2>&1
    if (( $? )) ; then
        test_failed $tid "diff"
    else
        test_passed $tid
        rm -f $tids.out $tids.diff
    fi
fi

# ================================================================
# Test 003 - /webserver/info test
# ================================================================
(( tid++ ))
tids=$(printf 'test%03d' $tid)
test_banner $tid
set -x
wget http://localhost:$Port/webserver/info -O $tids.out
st=$?
set +x
if (( $st )) ; then
    test_failed $tid "wget"
else
    grep 'Configuration Options' $tids.out
    if (( $? )) ; then
        test_failed $tid "diff"
    else
        test_passed $tid
        rm -f $tids.out
    fi
fi

# ================================================================
# Test 004 - /scripts/scripts.sh
# ================================================================
(( tid++ ))
tids=$(printf 'test%03d' $tid)
test_banner $tid
set -x
wget http://localhost:$Port/scripts/script.sh -O $tids.out
st=$?
set +x
if (( $st )) ; then
    test_failed $tid "wget"
else
    diff $tids.out $tids.ok >$tids.diff 2>&1
    if (( $? )) ; then
        test_failed $tid "diff"
    else
        test_passed $tid
        rm -f $tids.out $tids.diff
    fi
fi

# ================================================================
# Test 005 - /scripts/scripts.sh! - execute
# ================================================================
(( tid++ ))
tids=$(printf 'test%03d' $tid)
test_banner $tid
set -x
wget "http://localhost:$Port/scripts/script.sh!" -O $tids.out
st=$?
set +x
if (( $st )) ; then
    test_failed $tid "wget"
else
    diff $tids.out $tids.ok >$tids.diff 2>&1
    if (( $? )) ; then
        test_failed $tid "diff"
    else
        test_passed $tid
        rm -f $tids.out $tids.diff
    fi
fi

# ================================================================
# Test 006 - /scripts/scripts.sh! - execute, treat as HTML
# ================================================================
(( tid++ ))
tids=$(printf 'test%03d' $tid)
test_banner $tid
set -x
wget "http://localhost:$Port/scripts/script.sh!?content-type=text/html" -O $tids.out
st=$?
set +x
if (( $st )) ; then
    test_failed $tid "wget"
else
    diff $tids.out $tids.ok >$tids.diff 2>&1
    if (( $? )) ; then
        test_failed $tid "diff"
    else
        test_passed $tid
        rm -f $tids.out $tids.diff
    fi
fi

kill_webserver $Port

# ================================================================
# Test 007 - daemon test
# ================================================================
(( tid++ ))
tids=$(printf 'test%03d' $tid)
test_banner $tid
Port=$(( $PortBase + $tid ))
kill_webserver $Port
set -x
$Webserver --extra "testid=$tids" \
           --port $Port \
           --webdir $RootDir/www \
           -L debug \
           --daemonize \
           --log-file $tids.log \
           --pid-file $tids.pid
st=$?
set +x
if (( $st )) ; then
    test_failed $tid "webserver"
else
    sleep 1
    set -x
    wget http://localhost:$Port -O $tids.out
    st=$?
    set +x
    if (( $st )) ; then
        test_failed $tid "wget"
    else
        diff $tids.out $tids.ok >$tids.diff 2>&1
        if (( $? )) ; then
            test_failed $tid "diff"
        else
            test_passed $tid
            rm -f $tids.out $tids.diff $tids.log $tids.pid
        fi
    fi
fi

#kill %1 - won't work for a daemon
# must be mac and linux compatible
kill_webserver $Port

# ================================================================
# Test 008 - HTTPS test.
# ================================================================
(( tid++ ))
tids=$(printf 'test%03d' $tid)
test_banner $tid
Port=$(( $PortBase + $tid ))
kill_webserver $Port
set -x
$Webserver --extra "testid=$tids" \
           --port $Port \
           --webdir $RootDir/www \
           -L debug \
           --port 8443 \
           --https \
           --cert $RootDir/certs/webserver.pem &
st=$?
set +x
if (( $st )) ; then
    test_failed $tid "webserver"
else
    sleep 2
    set -x
    ## wget does not seem to work correctly for HTTPS
    ##wget --no-check-certificate --tries 5 "https://localhost:8443" -O $tids.out
    curl -k -o $tids.out https://localhost:8443
    st=$?
    set +x
    if (( $st )) ; then
        test_failed $tid "curl"
    else
        diff $tids.out $tids.ok >$tids.diff 2>&1
        if (( $? )) ; then
            test_failed $tid "diff"
        else
            test_passed $tid
            rm -f $tids.out $tids.diff
        fi
    fi
fi

kill_webserver $Port

# ================================================================
# Test 009 - plugin test
# ================================================================
(( tid++ ))
tids=$(printf 'test%03d' $tid)
test_banner $tid
Port=$(( $PortBase + $tid ))
kill_webserver $Port
set -x
$Webserver --extra "testid=$tids" \
           --port $Port \
           --webdir $RootDir/www \
           -L debug \
           --plugin $RootDir/www/plugins/default.py &
st=$?
set +x
if (( $st )) ; then
    test_failed $tid "webserver"
else
    sleep 1
    set -x
    wget http://localhost:$Port -O $tids.out
    st=$?
    set +x
    if (( $st )) ; then
        test_failed $tid "wget"
    else
        diff $tids.out $tids.ok >$tids.diff 2>&1
        if (( $? )) ; then
            test_failed $tid "diff"
        else
            test_passed $tid
            rm -f $tids.out $tids.diff
        fi
    fi
fi

kill_webserver $Port

# ================================================================
# Test 010 - detect invalid option
# ================================================================
(( tid++ ))
tids=$(printf 'test%03d' $tid)
test_banner $tid
set -x
$Webserver --port 100000
st=$?
set +x
if (( $st )) ; then
    test_passed $tid
else
    test_failed $tid "webserver"
fi

# ================================================================
# Test 011 - template test
# ================================================================
(( tid++ ))
tids=$(printf 'test%03d' $tid)
test_banner $tid
Port=$(( $PortBase + $tid ))
kill_webserver $Port
set -x
$Webserver --extra "testid=$tids" \
           --port $Port \
           --webdir $RootDir/www \
           -L debug &
st=$?
set +x
if (( $st )) ; then
    test_failed $tid "webserver"
else
    sleep 1
    set -x
    #curl -k -o $tids.out "http://localhost:$Port/templates/test.tmpl?title=Template%20Test&arg1=foo&arg2=42"
    wget "http://localhost:$Port/templates/test.tmpl?title=Template%20Test&arg1=foo&arg2=42" -O $tids.out
    st=$?
    set +x
    if (( $st )) ; then
        test_failed $tid "wget"
    else
        diff $tids.out $tids.ok >$tids.diff 2>&1
        if (( $? )) ; then
            test_failed $tid "diff"
        else
            test_passed $tid
            rm -f $tids.out $tids.diff
        fi
    fi
fi

kill_webserver $Port

# ================================================================
# Done.
# ================================================================
banner 'Done'
if (( ${#FailedIds[@]} > 0 )) ; then
    fids="(${FailedIds[@]})"
fi
printf 'Summary\n'
printf '   Passed: %3d\n' $Passed
printf '   Failed: %3d  %s\n' $Failed "$fids"
printf '   Total:  %3d\n' $Total

exit $Failed

