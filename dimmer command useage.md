
# turn sink off
# {"topic":"RVC/DC_DIMMER_COMMAND_2/46","payload":{"command":2,"command definition":"on delay","data":"2EFFC802FF00FFFF","delay/duration":255,"desired level":100,"dgn":"1FEDB","group":"11111111","instance":46,"interlock":"00","interlock definition":"no interlock active","name":"DC_DIMMER_COMMAND_2","timestamp":"1672729400.286914"},"qos":0,"retain":false,"_msgid":"856dfbf8367ae7dd"}
#  turn sink on
# {"topic":"RVC/DC_DIMMER_COMMAND_2/46","payload":{"command":2,"command definition":"on delay","data":"2EFFC802FF00FFFF","delay/duration":255,"desired level":100,"dgn":"1FEDB","group":"11111111","instance":46,"interlock":"00","interlock definition":"no interlock active","name":"DC_DIMMER_COMMAND_2","timestamp":"1672729400.286914"},"qos":0,"retain":false,"_msgid":"856dfbf8367ae7dd"}


        
    case "Bedroom Ceiling Lights A":
    loadId = 25;
    dimmable = "yes";
    break;
    
    case "Over Bed Ceiling Lights B":
    loadId = 26;
    dimmable = "yes";
    break;
    
    case "Bedroom Vanity":
    loadId = 28;
    dimmable = "yes";
    break;
    
    case "Bedroom Accent Lights":
    loadId = 27;
    dimmable = "yes";
    break;
     
    case "Courtesy Lights":
    loadId = 29;
    dimmable = "yes";
    break;
    
    case 'Rear Bath Ceiling Lights':
    loadId = 30;
    dimmable = "yes";
    break;
    
    case 'Rear Bath Lav Lights':
    loadId = 31;
    dimmable = "yes";
    break;
    
    case 'Rear Bath Accent Lights':
    loadId = 32;
    dimmable = "yes";
    break;
    
    case "Mid Bath Ceiling Light":
    loadId = 33;
    dimmable = "yes";
    break;
    
    case 'Mid Bath Accent Light':
    loadId = 34;
    dimmable = "yes";
    break;
    
    case 'Entry Ceiling Light':
    loadId = 35;
    dimmable = "yes";
    break;

    case "Living Room Edge Accent Lights":
    loadId = 36;
    dimmable = "no";
    break;
    
    case "Living Room Ceiling A Lights":
    loadId = 37;
    dimmable = "no";
    break;
    
    case 'Living Room Ceiling B Lights':
    loadId = 38;
    dimmable = "no";
    break;
    
    case 'Living Room Ceiling Accent A':
    loadId = 39;
    dimmable = "no";
    break;
 
    case 'Living Room Ceiling Accent B':
    loadId = 40;
    dimmable = "no";
    break;   

    case 'Living Room Misc B':
    loadId = 41;
    dimmable = "no";
    break; 

    case "Porch Light":
    loadId = 42;
    dimmable = "no";
    break;
    
    case 'Cargo Lights':
    loadId = 43;
    dimmable = "no";
    break;
    
    case 'DS Security Light':
    loadId = 44;
    dimmable = "no";
    break;
    
    case "Dinette Light":
    loadId = 45;
    dimmable = "no";
    break;
    
    case 'Sink Lights':
    loadId = 46;
    dimmable = "no";
    break;

    case 'Midship Lights':
    loadId = 47;
    dimmable = "no";
    break;

    case 'Awning Lights DS':
    loadId = 51;
    dimmable = "no";
    break;

    case 'Awning Lights PS':
    loadId = 52;
    dimmable = "no";
    break;

    case 'Cargo Lights':
    loadId = 53;
    dimmable = "no";
    break;

    case 'Under Slideout Lights':
    loadId = 54;
    dimmable = "no";
    break;

    case 'Closet Lights':
    loadId = 55;
    dimmable = "no";
    break;       
    
    case 'Bed Reading Lights':
    loadId = 56;
    dimmable = "no";
    break;

    case 'Security Lights DS':
    loadId = 57;
    dimmable = "no";
    break;

    case 'Security Lights PS':
    loadId = 58;
    dimmable = "no";
    break;    

    case 'Security Lights Motion Sensor':
    loadId = 59;
    dimmable = "no";
    break;    

    case 'Porch Light':
    loadId = 60;
    dimmable = "no";
    break;

    default:
}

    //Active for non-dimmable (relay) ON instances:
if (msg.on === true  && msg.on_off_command === true && dimmable === 'no' )  {
    onCommand = 2
    payload = loadId + " " + onCommand ;
}
    //Active for dimmable ON instances - revert to previous brightness setting:
if (msg.on === true && msg.bri > 0 && msg.on_off_command === true && dimmable === "yes") {
    payload = loadId + " " + onCommand + " " + toggle ; //Change Toggle to noToggle if full brightness desired with ON
}
    //Active if try to dim relay instances:
if (msg.on === true && msg.bri > 0 && msg.on_off_command === false && dimmable === "no")  {
    onCommand = 2
    payload = loadId + " " + onCommand ;
    node.warn ("Cannot DIM Relay Channels") ; // do not dim relay circuits!
}  
    //Active when brightness value sent for dimmable instances
if (msg.on === true && msg.bri > 0 && msg.on_off_command === false && dimmable === "yes") {
    payload = loadId + " " + onCommand + " " + msg.bri ;
}
    //Acitve for all OFF instances
if (msg.on === false)  {
    payload = loadId + " " + offCommand ;
}

let msg1 = {
     payload
  };


  return [ msg1 ];
  
  
//
// Copyright (C) 2019 Wandertech LLC
// Copyright (C) eRVin project mods 2020
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program.  If not, see <https://www.gnu.org/licenses/>.

// Input: the JSON output of DC_DIMMER_STATUS_3/# for a light.
// Output 1: "dim", "on" or "off" payload to set toggle switch indicator.
// Output 2: brightness level (0-100) to set optional slider value.
//
// Also saves the on/off status and brightness into global 'status'
// context for use by other nodes.
//
// Built-in RBE functionality only outputs messages if the value has
// changed from the previously recorded value.

var instance = msg.payload.instance;
var brightness = msg.payload['operating status (brightness)'];
var previous = global.get('status').lights[instance];

// eRVin mod: Instead of just on/off for all lights, distinguish between dimable and 
// non-dimmable and off. One reason for this is to allow use of a global variable 'onmode'
// to allow the user a choice between full on and previous dim value. for proper operation
// configure the dashboard switch nodes so dimmable lights have 
// an ON PAYLOAD = dim, and non-dimmable have an ON PAYLOAD = on. Appropriate
// changes have also been made to accomadate this in the command_dc_dimmer_ervin.js
// 
// The below line tests for brightness = 100 and if true command is set = 'on',
// if not it falls thru and tests for brightness > 0. If true it sets command = 'dim',
// if not it falls thru and sets command = 'off'
//  
var command = (brightness == 100) ? 'on' : (brightness > 0) ? 'dim' : 'off';
//var command = (brightness > 0) ? 'dim' : 'off';

var msg1 = null;
var msg2 = null;

// Only send a message if the value has changed.
if (previous.state != command) {
  if (previous) {
    global.set('status.lights[' + instance + '].state', command);
  }
  msg1 = { 'payload': command };
}

if (previous.brightness != brightness && brightness <= 100) {
  global.set('status.lights[' + instance + '].brightness', brightness);
  msg2 = { 'payload': brightness };
}

return [ msg1, msg2 ];

