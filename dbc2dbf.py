
# DESC: dbc2dbf is the conversion tool to convert Vector CAN DBC to Busmaster DBF file.
# AUTHOR: Tony (Thuong. Bui)

import re
import sys

def parse_dbc(dbc_content):
    messages = []
    current_message = None
    protocol_type = "CAN"  # Default protocol type
    message_attributes = {}  # Dictionary to store message attributes
    value_tables = {}  # Dictionary to store value tables for signals

    for line in dbc_content.splitlines():
        print(f"Line: {line}")

        # Check for ProtocolType attribute
        protocol_match = re.match(r'^BA_ "ProtocolType" "(.*?)";', line)
        if protocol_match:
            protocol_type = protocol_match.group(1)
            print(f">> Protocol type set to {protocol_type}")

        # Match message definitions
        message_match = re.match(r'^BO_ (\d+) (\w+): (\d+) (\w+)', line)
        if message_match:
            print(f">> Found message")
            if current_message:
                print(">> Append message")
                messages.append(current_message)
            message_id, message_name, message_length, message_node = message_match.groups()
            current_message = {
                'id': int(message_id),
                'name': message_name,
                'length': int(message_length),
                'node': message_node,
                'signals': [],
                'attributes': {}
            }
            continue

        # Match signal definitions with scientific notation
        signal_match = re.match(r'^\s*SG_ (\w+) : (\d+)\|(\d+)@(\d+)([+-]) \(([\d.]+),([\d.-]+)\) \[([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?|\d*\.?\d+)\|([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?|\d*\.?\d+)\] "(.*?)"\s+(\w+)',line)
        
        if signal_match :
            print(">> Found signal")
            if current_message:
                signal_name, start_bit, signal_length, byte_order, value_type, factor, offset, min_val, max_val, unit, receiver = signal_match.groups()
                current_message['signals'].append({
                    'name': signal_name,
                    'start_bit': int(start_bit),
                    'length': int(signal_length),
                    'byte_order': byte_order,
                    'value_type': value_type,
                    'factor': float(factor),
                    'offset': float(offset),
                    'phy_min_val': float(min_val),
                    'phy_max_val': float(max_val),
                    'unit': unit,
                    'receiver': receiver,
                    'value_table': {}  # Initialize an empty dictionary for value table
                })
        # Match message attributes
        attribute_match = re.match(r'^BA_ "(\w+)" BO_ (\d+) (\w+);', line)
        if attribute_match:
            attr_name, msg_id, attr_value = attribute_match.groups()
            msg_id = int(msg_id)
            if msg_id not in message_attributes:
                message_attributes[msg_id] = {}
            message_attributes[msg_id][attr_name] = attr_value
            print(f">> Found attribute for message {msg_id}: {attr_name} = {attr_value}")

        # Match value tables
        value_table_match = re.match(r'^VAL_ (\d+) (\w+) (.+);', line)
        if value_table_match:
            msg_id, signal_name, value_pairs = value_table_match.groups()
            msg_id = int(msg_id)
            value_table = {}
            # Parse the value-description pairs
            for value, description in re.findall(r'(\d+) "(.*?)"', value_pairs):
                value_table[int(value)] = description
            # Store the value table in the appropriate signal
            for message in messages:
                if message['id'] == msg_id:
                    for signal in message['signals']:
                        if signal['name'] == signal_name:
                            signal['value_table'] = value_table
                            print(f">> Found value table for signal {signal_name}: {value_table}")

    if current_message:
        print(">> Append last message")
        messages.append(current_message)

    #Adding message attributes
    for message in messages:
        if message['id'] in message_attributes:
            message['attributes'] = message_attributes[message['id']]

    return messages, protocol_type

def convert_to_dbf(messages, dbf_file_path):
 # Separate messages based on VFrameFormat
    j1939_messages = [msg for msg in messages if msg['attributes'].get('VFrameFormat') == '3']
    can_messages = [msg for msg in messages if msg['attributes'].get('VFrameFormat') in ['1', '2']]

    # Create DBF content for J1939 messages
    j1939_content = [
        "//******************************BUSMASTER Messages and signals Database ******************************//",
        "[DATABASE_VERSION] 1.3",
        "[PROTOCOL] J1939",
        "[BUSMASTER_VERSION] [3.2.2]",
        f"[NUMBER_OF_MESSAGES] {len(j1939_messages)}"
    ]

    for message in j1939_messages:
        num_signals = len(message['signals'])
        extMsg = "S"
        messageID = message['id'] & 0x0FFFFFFF
        if (message['id'] & 0x80000000) > 0:
            extMsg = "X"
        j1939_content.append(f"\r\n[START_MSG] {message['name']},{messageID},{message['length']},{num_signals},1,{extMsg}")

        for attr_name, attr_value in message['attributes'].items():
            j1939_content.append(f"[ATTRIBUTE] {attr_name} = {attr_value}")

        for signal in message['signals']:
            if signal['length'] > 0 :
                byte_index = (signal['start_bit'] // 8) + 1  # Offset by 1
                bit_index = signal['start_bit'] % 8

                # Decide the signal type and range
                value_type = "B"
                raw_max = 1
                raw_min = 0
                if signal['length'] > 1:
                    #---calculate from phy value from DBC---
                    #raw_max = (signal['phy_max_val'] - signal['offset'])/signal['factor']
                    #raw_min = (signal['phy_min_val'] - signal['offset'])/signal['factor']
                    
                    #---calculate from data type's range and bit length---
                    value_type = "U"
                    range = (1 << signal['length']) - 1
                    raw_max = range
                    raw_min = 0           
                    if(signal['value_type']) == "-":
                        value_type = "I"
                        raw_max = int(range/2)
                        raw_min = - int(range/2) - 1
                j1939_content.append(f"[START_SIGNALS] {signal['name']},{signal['length']},{byte_index},{bit_index},{value_type},{raw_max},{raw_min},{signal['byte_order']}, {signal['offset']},{signal['factor']},{signal['unit']},")
        
                # Add value descriptions
                for value, description in signal['value_table'].items():
                    j1939_content.append(f"[VALUE_DESCRIPTION] {description},{value}")
    
        j1939_content.append("[END_MSG]")

    # Write J1939 messages to file
    with open("J1939_"+ dbf_file_path, 'w') as j1939_file:
        j1939_file.write("\n".join(j1939_content))

    #------------------------------------------------------------
    # Create DBF content for CAN messages
    can_content = [
        "//******************************BUSMASTER Messages and signals Database ******************************//",
        "[DATABASE_VERSION] 1.3",
        "[PROTOCOL] CAN",
        "[BUSMASTER_VERSION] [3.2.2]",
        f"[NUMBER_OF_MESSAGES] {len(can_messages)}"
    ]

    for message in can_messages:
        num_signals = len(message['signals'])
        extMsg = "S"
        messageID = message['id'] & 0x0FFFFFFF
        if (message['id'] & 0x80000000) > 0:
            extMsg = "X"
        can_content.append(f"\r\n[START_MSG] {message['name']},{messageID},{message['length']},{num_signals},1,{extMsg}")

        for attr_name, attr_value in message['attributes'].items():
            can_content.append(f"[ATTRIBUTE] {attr_name} = {attr_value}")

        for signal in message['signals']:
            if signal['length'] > 0 :
                byte_index = (signal['start_bit'] // 8) + 1  # Offset by 1
                bit_index = signal['start_bit'] % 8

                #decide the signal type and range
                value_type = "B"
                raw_max = 1
                raw_min = 0
                if signal['length'] > 1 :
                    #---calculate from phy value from DBC---
                    #raw_max = (signal['phy_max_val'] - signal['offset'])/signal['factor']
                    #raw_min = (signal['phy_min_val'] - signal['offset'])/signal['factor']
                    
                    #---calculate from data type's range and bit length---
                    value_type = "U"
                    range = (1 << signal['length']) - 1
                    raw_max = range
                    raw_min = 0           
                    if(signal['value_type']) == "-":
                        value_type = "I"
                        raw_max = int(range/2)
                        raw_min = - int(range/2) - 1
                        
                can_content.append(f"[START_SIGNALS] {signal['name']},{signal['length']},{byte_index},{bit_index},{value_type},{raw_max},{raw_min},{signal['byte_order']}, {signal['offset']},{signal['factor']},{signal['unit']},")

                # Add value descriptions
                for value, description in signal['value_table'].items():
                    can_content.append(f"[VALUE_DESCRIPTION] {description},{value}")


        can_content.append("[END_MSG]")

    # Write CAN messages to file
    with open("CAN_"+dbf_file_path, 'w') as can_file:
        can_file.write("\n".join(can_content))

def main(dbc_file_path, dbf_file_path):
    # Read the DBC file
    with open(dbc_file_path, 'r') as dbc_file:
        dbc_content = dbc_file.read()

    # Parse and convert the DBC content
    messages, protocol_type = parse_dbc(dbc_content)
    convert_to_dbf(messages, dbf_file_path)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python script.py <path_to_dbc_file> <path_to_dbf_file>")
    else:
        dbc_file_path = sys.argv[1]
        dbf_file_path = sys.argv[2]
        main(dbc_file_path, dbf_file_path)
        
