/*
#   Copyright (C) 2020 Sean D'Epagnier
#
# This Program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.  

#   Modified (C) 2020 JF for Cybele Services (jf@netcys.com)

*/


function openTab(evt, tabName) {
    var i, x, tablinks;
    x = document.getElementsByClassName("tab");
    for (i = 0; i < x.length; i++) {
         x[i].style.display = "none";
    }
    tablinks = document.getElementsByClassName("tablink");
    for (i = 0; i < x.length; i++) {
        tablinks[i].className = tablinks[i].className.replace(" w3-red", "");
        tablinks[i].className = tablinks[i].className.replace(" active", "");
    }
    document.getElementById(tabName).style.display = "block";
      evt.currentTarget.firstElementChild.className += " w3-red";
      evt.currentTarget.firstElementChild.className += " active";
    currentTab = tabName;

    setup_watches()
}

var setup_watches = false;
var watches = {};

currentTab="Control";

$(document).ready(function() {
    namespace = '';
    $('#ping-pong').text("N/A");
    $('#connection').text('not connected');
    $('#imu_heading').text("N/A");
    $('#pitch').text("N/A");
    $('#roll').text("N/A");
    $('#heel').text("N/A");
    $('#rudder').text("N/A");
    $('#power_consumption').text("N/A");

    // Connect to the Socket.IO server.
    var port = location.port;
    port = cypilot_web_port;
    var socket = io.connect(location.protocol + '//' + document.domain + ':' + port + namespace);

    function show_gains() {
        var x = document.getElementsByClassName('gain');
        for (i = 0; i < x.length; i++)
            x[i].style.display = 'none';

        pilot =$('#pilot').val();
        x = document.getElementsByClassName('pilot'+pilot);
        for (i = 0; i < x.length; i++)
            x[i].style.display = 'inline';
    }
    
    // Event handler for new connections.
    var servo_command = 0, servo_command_timeout=0;
    var gains = [];
    var conf_names = [];
    socket.on('cypilot_values', function(msg) {
        watches = {};
        var list_values = JSON.parse(msg);
        $('#connection').text('connected');
        $('#aperrors0').text("");
        $('#aperrors1').text("");

        // control
        cypilot_watch('ap.enabled');
        cypilot_watch('ap.mode');

        cypilot_watch('ap.heading_command', .5);

        // gain
        cypilot_watch('ap.pilot');
        $('#gain_container').text('');

        $('#gain_container').append('<div class="w3-row">Pilot&emsp;<select id="pilot">');
        if('ap.pilot' in list_values && 'choices' in list_values['ap.pilot']) {
            var pilots = list_values['ap.pilot']['choices'];
            for (var pilot in pilots)
                $('#pilot').append('<option value="' + pilots[pilot] + '">' + pilots[pilot] + '</option');
        }

        $('#gain_container').append('</select></div>')

        $('#pilot').change(function(event) {
            cypilot_set('ap.pilot', $('#pilot').val());
            show_gains();
        });
        
        gains = [];
        for (var name in list_values)
            if('AutopilotGain' in list_values[name] && name.substr(0, 3) == 'ap.')
                gains.push(name);

        for (var i = 0; i<gains.length; i++) {
            var w = $(window).width();
            var sp = gains[i].split('.');
            var subname = sp[3];
            var pilot = sp[2];
            var info = list_values[gains[i]];
            var min = info['min'];
            var max = info['max'];
            var iname = 'gain'+pilot+subname
            $('#gain_container').append('<div class="gain pilot' + pilot + '"><p>'+subname+' <input type="range" id="' + iname + '" min="' + min + '" max="' + max + '" value = "' + 0 + '" step=".0001" style="width:'+w*3/4+'px" name="'+gains[i]+'"></input><span id="' + iname + 'label"></span></div>');
            $('#'+iname).change(function(event) {
                cypilot_set(this.name, this.valueAsNumber);
            });
        }

        // calibration
        cypilot_watch('imu.heading_offset', .5);
        cypilot_watch('imu.alignmentQ', .5);
        cypilot_watch('imu.alignmentCounter', .25);

        cypilot_watch('rudder.offset')
        cypilot_watch('rudder.scale')
        cypilot_watch('rudder.nonlinearity')
        cypilot_watch('rudder.range')
        cypilot_watch('rudder.calibrated')

        // configuration
        $('#configuration_container').text('')
        conf_names = [];
        for (var name in list_values)
            // if(list_values[name]['type'] == 'RangeSetting')
            //    conf_names.push(name); // remove ap.
            if('units' in list_values[name] && list_values[name]['units'] != '')
                conf_names.push(name);

        conf_names.sort();

        for (var i = 0; i<conf_names.length; i++) {
            var name = conf_names[i];
            var info = list_values[name];

            var min = info['min'];
            var max = info['max'];
            var unit = info['units'];

            var iname = 'confname'+i;

            $('#configuration_container').append('<div class="w3-row"><div class="w3-col s4 m4 l4">' + name + '</div><div class="w3-col s3 m3 l3"><input type="range" id="'+iname+'" min="' + min + '" max="' + max + '" step=".01" value="2" style="width: 200px" name="'+name+'"></input></div><div class="w3-col s2 m2 l2"><span id="'+ iname+'label"></span></div><div class="w3-col s3 m3 l3">' + unit + '</div></div>');
            $('#'+iname).change(function(event) {
                cypilot_set(this.name, this.valueAsNumber);
            });
        }

        cypilot_watch('servo.controller');
        cypilot_watch('servo.flags');

        setup_watches();
    });

    socket.on('cypilot_disconnect', function() {
        $('#connection').text('Disconnected')
    });

    // update manual servo command
    setTimeout(poll_cypilot, 1000)
    function poll_cypilot() {
        setTimeout(poll_cypilot, 1000)
        if(servo_command_timeout > 0) {
            if(servo_command_timeout-- <= 0)
                servo_command = 0;
            cypilot_set('servo.command', servo_command);
        }
    }
    
    // Event handler for server sent data.
    socket.on('log', function(msg) {
        $('#log').append(msg + "<br>");
    });
    
    // Interval function that tests message latency by sending a "ping"
    var ping_pong_times = [];
    var start_time;
    window.setInterval(function() {
        start_time = (new Date).getTime();
        socket.emit('ping');
    }, 5000);
    
    // Handler for the "pong" message. When the pong is received, the
    socket.on('pong', function() {
        var latency = (new Date).getTime() - start_time;
        ping_pong_times.push(latency);
        ping_pong_times = ping_pong_times.slice(-30); // keep last 30 samples
        var sum = 0;
        for (var i = 0; i < ping_pong_times.length; i++)
            sum += ping_pong_times[i];
        $('#ping-pong').text(Math.round(10 * sum / ping_pong_times.length) / 10);
    });
    
    var heading = 0;
    var heading_command = 0;
    var heading_set_time = new Date().getTime();
    var heading_local_command;
    var last_rudder_data = {}
    var rudder_calibrated = 0;

    function heading_str(heading) {
        if(heading.toString()=="false")
            return "N/A"

        // round to 1 decimal place
        heading = Math.round(10*heading)/10

        mode = $('#mode').val()
        if(mode == 'wind' || mode == 'true wind') {
            if(heading > 0)
               heading += '-';
        }
        return heading
    }

    socket.on('cypilot', function(msg) {
        data = JSON.parse(msg);

        if('ap.mode' in data) {
            value = data['ap.mode'];
            $('#mode').val(value);
            $('#mode_display').text(data['ap.mode']);
        }

        if('ap.heading' in data) {
            heading = data['ap.heading'];
            if(heading.toString()=="false")
                $('#aperrors0').text('compass or gyro failure!');
            else
                $('#aperrors0').text('');
            $('#heading').text(heading_str(heading));
        }

        if('ap.enabled' in data) {
            if(data['ap.enabled']) {
                var w = $(window).width();
                $('#tb_engaged button').css('left', w/12+"px");
                $('#tb_engaged').addClass('toggle-button-selected');

                $('#port10').text('10');
                $('#port_1').text('1');
                $('#star_1').text('1');
                $('#star10').text('10');
            } else {
                $('#tb_engaged button').css('left', "0px")
                $('#tb_engaged').removeClass('toggle-button-selected');

                $('#port10').text('<<');
                $('#port_1').text('<');
                $('#star_1').text('>');
                $('#star10').text('>>');
            }
        }

        if('ap.pilot' in data) {
            value= data['ap.pilot'];
            $('#pilot').val(value);
            show_gains();
        }

        for (var i = 0; i<gains.length; i++)
            if(gains[i] in data) {
                value = data[gains[i]]
                var sp = gains[i].split('.');
                var subname = sp[3];
                var pilot = sp[2];
                var iname = 'gain'+pilot+subname
                if(value != $('#' + iname).valueAsNumber) {
                    $('#' + iname).val(value);
                    $('#' + iname + 'label').text(value);
                }
            }
        if('ap.heading_command' in data) {
            heading_command = data['ap.heading_command'];
            mode = $('#mode').val()
            if(mode == 'rudder angle')
                $('#heading_command').text(heading_str(-heading_command));
            else
                $('#heading_command').text(heading_str(heading_command));
        }

        if('servo.engaged' in data) {
            if(data['servo.engaged'])
                $('#servo_engaged').text('Engaged');
            else
                $('#servo_engaged').text('Disengaged');
        }

        // calibration
        if('imu.heading' in data)
            $('#imu_heading').text(data['imu.heading']);
        if('imu.pitch' in data)
            $('#pitch').text(data['imu.pitch']);
        if('imu.roll' in data)
            $('#roll').text(data['imu.roll']);
        if('imu.heel' in data)
            $('#heel').text(data['imu.heel']);
        if('imu.alignmentCounter' in data)
            $('.myBar').width((100-data['imu.alignmentCounter'])+'%');
        if('imu.heading_offset' in data)
            $('#imu_heading_offset').val(data['imu.heading_offset']);
        var rudder_dict = {'rudder.offset': 'Offset',
                           'rudder.scale': 'Scale',
                           'rudder.nonlinearity': 'Non Linearity',
                           'rudder.range': 'Rudder Range'};
        if('rudder.calibrated' in data)
        {
            rudder_calibrated = data['rudder.calibrated'];
            if(rudder_calibrated) {
                $('#rudder_centered')[0].disabled = true
                $('#rudder_starboard_range')[0].disabled = true
                $('#rudder_port_range')[0].disabled = true
                $('#rudder_range').attr('disabled','disabled')
            } else {
                $('#rudder_centered')[0].disabled = false
                $('#rudder_starboard_range')[0].disabled = false
                $('#rudder_port_range')[0].disabled = false
                $('#rudder_range').attr('disabled',null)
            }
        }
        if( rudder_calibrated ) {
            if('rudder.angle' in data) {
                $('#rudder').text(data['rudder.angle']);
                $('#rudder').append('<p>')
                for(var name in rudder_dict)
                    if(name in last_rudder_data)
                        $('#rudder').append(' ' + rudder_dict[name] + ' ' + Math.round(100*last_rudder_data[name])/100);
            }
        }
        else {
            $('#rudder').text('Not calibrated');
            $('#rudder').append('<p>')
            $('#rudder').append('Set rudder range and enter port, starboard, and center rudder position')
        }

        for(var name in rudder_dict)
            if(name in data)
                last_rudder_data[name] = data[name];

        if('rudder.range' in data)
            $('#rudder_range').val(data['rudder.range']);

        // configuration
        for(i=0; i < conf_names.length; i++) {
            if(conf_names[i] in data) {
                value = data[conf_names[i]];
                var iname = 'confname'+i;
                $('#' + iname).val(value);
                $('#' + iname + 'label').text(value);
            }
        }

        // statistics
        if('servo.amp_hours' in data) {
            value = data['servo.amp_hours'];
            $('#amp_hours').text(Math.round(1e4*value)/1e4);
        }

        if('servo.voltage' in data) {
            value = data['servo.voltage'];
            $('#voltage').text(Math.round(1e3*value)/1e3);
        }
        
        if('servo.controller_temp' in data) {
            value = data['servo.controller_temp'];
            $('#controller_temp').text(value);
        }

        if('servo.controller' in data) {
            value = data['servo.controller'];
            if(value == 'none')
                $('#aperrors1').text('no motor controller!');
            else
                $('#aperrors1').text('');
        }

        if('servo.flags' in data)
            $('#servoflags').text(data['servo.flags']);
    });
    
    function cypilot_set(name, value) {
        socket.emit('cypilot', name + '=' + JSON.stringify(value));
    }

    function cypilot_watch(name, period=true) {
        if(period === false && !(name in watches && watches[name]))
            return; // already not watching, no need to inform server
        watches[name] = period;
        socket.emit('cypilot', 'watch={"' + name + '":' + JSON.stringify(period) + '}')
    }

    // Control
    $('.toggle-button').click(function(event) {
        if($(this).hasClass('toggle-button-selected')) {
            cypilot_set('ap.enabled', false)
        } else {
            mode = $('#mode').val()
            if(mode == 'rudder angle')
                heading = 0;
            cypilot_set('ap.heading_command', heading)
            cypilot_set('ap.enabled', true)
        }
    });
    
    move = function(x) {
        var engaged = $('#tb_engaged').hasClass('toggle-button-selected');
        if(engaged) {
            time = new Date().getTime()
            if(time - heading_set_time > 1000)
                heading_local_command = heading_command;
            heading_set_time = time;
            heading_local_command += x;
            cypilot_set('ap.heading_command', heading_local_command);
        }
        /* else {
            if(x != 0) {
                sign = x > 0 ? 1 : -1;
                servo_command = -sign;
                servo_command_timeout = Math.abs(x) > 5 ? 3 : 1;
            }
        }
        */
    }

    $('#mode').change(function(event) {
        cypilot_set('ap.mode', $('#mode').val());
    });
    
    $('#port10').click(function(event) { move(-10); });
    $('#port_1').click(function(event) { move(-1); });
    $('#star_1').click(function(event) { move(1); });
    $('#star10').click(function(event) { move(10); });

    // Gain

    // Calibration
    $('#level').click(function(event) {
        cypilot_set('imu.alignmentCounter', 100);
        return false;
    });

    $('#imu_heading_offset').change(function(event) {
        cypilot_set('imu.heading_offset', $('#imu_heading_offset').value());
    });

    $('#rudder_centered').click(function(event) {
        if( ! rudder_calibrated )
            cypilot_set('rudder.calibration_state', 'centered');
    });

    $('#rudder_port_range').click(function(event) {
        if( ! rudder_calibrated )
            cypilot_set('rudder.calibration_state', 'port range');
    });

    $('#rudder_starboard_range').click(function(event) {
        if( ! rudder_calibrated )
            cypilot_set('rudder.calibration_state', 'starboard range');
    });

    $('#rudder_reset').click(function(event) {
        cypilot_set('rudder.calibration_state', 'reset');
    });
    
    $('#rudder_range').change(function(event) {
        cypilot_set('rudder.range', $('#rudder_range').value());
    });

    $('#rudder_move_starboard').click(function(event) {
        cypilot_set('servo.command', -0.1);
    });

    $('#rudder_move_port').click(function(event) {
        cypilot_set('servo.command', +0.1);
    });

    // Configuration

    // hack
    document.addEventListener('click', function(event) {
        var target = event.target;
        if (target.tagName.toLowerCase() == 'a')
        {
            if(target.getAttribute('href').match('33333')) {
                target.href = window.location.origin;
                target.port = 33333;
            }

        }
    }, false);

    // Statistics
    $('#reset_amp_hours').click(function(event) {
        cypilot_set('servo.amp_hours', 0);
        return false;
    });
    
    openTab("Control");

    function cypilot_watches(names, watch, period) {
        for(var i=0; i< names.length; i++)
            cypilot_watch(names[i], watch ? period : false);
    }
    
    // should be called if tab changes
    setup_watches = function() {
        var tab = currentTab;
        cypilot_watches(['ap.heading'], tab == 'Control', 0.5);
        cypilot_watches(gains, tab == 'Gain', 1);
        cypilot_watches(['imu.heading', 'imu.pitch', 'imu.roll', 'imu.heel', 'rudder.angle'], tab == 'Calibration', .5);
        cypilot_watches(conf_names, tab == 'Configuration', 1);
        cypilot_watches(['servo.amp_hours', 'servo.voltage', 'servo.controller_temp', 'servo.engaged'], tab == 'Statistics', 1);
    }
    setup_watches();
    
    function openTab(name) {
        var i;
        var x = document.getElementsByClassName("tabname");
        for (i = 0; i < x.length; i++) {
            x[i].style.display = "none";
        }
        document.getElementById(name).style.display = "block";
    }

    function window_resize() {
        var w = $(window).width();
        $(".font-resizable").each(function(i, obj) {
            if (w < 600)
                $(this).css('font-size', w/18+"px")
            else
                $(this).css('font-size', w/35+"px")
        });
        $(".font-resizable1").each(function(i, obj) {
            $(this).css('font-size', w/12+"px")
        });
        $(".font-resizable2").each(function(i, obj) {
            $(this).css('font-size', w/30+"px")
        });
        $(".font-resizable3").each(function(i, obj) {
            $(this).css('font-size', w/50+"px")
        });
        $(".button-resizable").each(function(i, obj) {
            $(this).css('width', w/5+"px")
            $(this).css('height', w/6+"px")
        });
        $(".button-resizable1").each(function(i, obj) {
            $(this).css('width', w/5+"px")
            $(this).css('height', w/18+"px")
        });
        $(".button-resizable2").each(function(i, obj) {
            $(this).css('width', w/8+"px")
            $(this).css('height', w/18+"px")
        });
        $(".toggle-button-selected button").each(function(i, obj) {
            $(this).css('left', w/12+"px")
        });
    }

    // Set the theme on page load
    setTheme( getCookie('theme') )

    // Bind setTheme action when the user change the theme via the radio buttons
    $('.theme_option').on('click', function(){ setTheme() })

    $(window).resize(window_resize);
    window_resize();
});

/**
 * When called, setTheme will read selected theme from fround .theme_option and change the theme.
 * 
 * @function setTheme
 * @param themeName {null|string} the name of the theme to apply or null value to read input.theme_option selection (default is null)
 * @return {string} The applyed theme name.
 *
 */
function setTheme( themeName=null ){

    if(themeName==null){
        themeName = $('input.theme_option:checked').val()
    }else{
        $('input.theme_option:checked').prop("checked", false);
        $("input.theme_option[value="+themeName+"]" ).prop("checked", true );
    }

    $('body').attr('theme', themeName )
    setCookie('theme', themeName)

    // The w3 framework use !important 213 times. So it's impossible to cascade over it. Therefor it must be disabled.
    if(themeName == 'dark'){
        $("link[href*='w3.css']").prop('disabled', true);
    }else{
        $("link[href*='w3.css']").prop('disabled', false);
    }

    return themeName
}

/**
 * Create or edit a cookie.
 * 
 * @function setCookie
 * @param key {string} The name of the cookie to set/edit.
 * @param value {string} The value you want to store.
 * @param expiry {int|number|null} The time to live of the cookie in days (default value is 365 days).
 * @return {void} This function does not return anything.
 *
 */
function setCookie(key, value, expiry=365) {
    var expires = new Date();
    expires.setTime(expires.getTime() + (expiry * 24 * 60 * 60 * 1000));
    document.cookie = key + '=' + value + ';expires=' + expires.toUTCString();
}

/**
 * Get the value of a cookie.
 * 
 * @function getCookie
 * @param key {string} the name of the cookie to query.
 * @return {string|null} Return the value of the cookie or null if the cooky is not found.
 *
 */
function getCookie(key) {
    var keyValue = document.cookie.match('(^|;) ?' + key + '=([^;]*)(;|$)');
    return keyValue ? keyValue[2] : null;
}
