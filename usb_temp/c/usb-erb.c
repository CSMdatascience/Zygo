/*
 *
 *  Copyright (c) 2006  Warren Jasper <wjasper@tx.ncsu.edu>
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA
 */

#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <asm/types.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <linux/hiddev.h>

#include "pmd.h"
#include "usb-erb.h"

#define FS_DELAY (1000)

/* reads digital port  */
__u8 usbDIn_USBERB(int fd, __u8 port)
{
  __u8 value;
  
  PMD_SendOutputReport(fd, DIN, &port, 1, FS_DELAY);
  PMD_GetInputReport(fd, DIN, &value, sizeof(value), FS_DELAY);
  return value;
}

/* writes digital port */
void usbDOut_USBERB(int fd, __u8 port, __u8 value) 
{
  __u8 cmd[2];
  
  cmd[0] = port;
  cmd[1] = value;

  PMD_SendOutputReport(fd, DOUT, cmd, sizeof(cmd), FS_DELAY);
}

/* reads digital port bit */
__u8 usbDBitIn_USBERB(int fd, __u8 port, __u8 bit) 
{
  __u8 cmd[2];
  __u8 value;

  cmd[0] = port;
  cmd[1] = bit;

  PMD_SendOutputReport(fd, DBIT_IN, cmd, sizeof(cmd), FS_DELAY);
  PMD_GetInputReport(fd, DBIT_IN, &value, sizeof(value), FS_DELAY);

  return value;
}

/* writes digital port bit */
void usbDBitOut_USBERB(int fd, __u8 port, __u8 bit, __u8 value)
{
  __u8 cmd[3];
  
  cmd[0] = port;
  cmd[1] = bit;
  cmd[2] = value;

  PMD_SendOutputReport(fd, DBIT_OUT, cmd, sizeof(cmd), FS_DELAY);
}

void usbReadMemory_USBERB(int fd, __u16 address, __u8 count, __u8* memory)
{
  /*
    The command reads data from the configuration memory (EEPROM).
    All of the memory may be read.  The USB hub chip EEPROM may be
    read, and its address range is 0x0400 - 0x04FF.
  */

  struct t_arg {
    __u16 address;
    __u8 type;
    __u8 count;
  } arg;

  if ( count > 62 ) count = 62;
  arg.type = 0;      // unused for this device.
  arg.address = address;
  arg.count = count;

  PMD_SendOutputReport(fd, MEM_READ, (__u8 *) &arg, sizeof(arg), FS_DELAY);
  PMD_GetInputReport(fd, MEM_READ, memory, count, FS_DELAY);
}

int usbWriteMemory_USBERB(int fd, __u16 address, __u8 count, __u8* data)
{
  /*
    This command writes to non-volatile EEPROM memory on the device.  The non-volatile
    memory is used to store calibration coefficients, system information, and user data.  Locations
    0x000-0x07F are reserved for firmware use and my not be written.  This device has external
    EEPROM for the USB hub chip configuration, and the values for that EEPROM may be written
    through this command.  The address range for the hub EEPROM is 0x0400-0x04FF.
  */
  
  int i;
  struct t_arg {
    __u16 address;
    __u8 count;
    __u8 data[count];
  } arg;

  if ( address <= 0x7f ) return -1;
  if ( count > 59 ) count = 59;
  
  arg.address = address;
  arg.count = count;
  for ( i = 0; i < count; i++ ) {
    arg.data[i] = data[i];
  }
  PMD_SendOutputReport(fd, MEM_WRITE, (__u8 *) &arg, sizeof(arg), FS_DELAY);
  return 0;
}

/* blinks the LED of USB device */
int usbBlink_USBERB(int fd)
{
  return PMD_SendOutputReport(fd, BLINK_LED, 0, 0, FS_DELAY);
}

/* resets the USB device */
int usbReset_USBERB(int fd)
{
  return PMD_SendOutputReport(fd, RESET, 0, 0, FS_DELAY);
}

__u16 usbGetStatus_USBERB(int fd)
{
  __u16 status;
  /*
    Bit 0: Port A polarity setting       (0 = inverted,  1 = normal)  (N/A on ERB08)
    Bit 1: Port B polarity setting       (0 = inverted,  1 = normal)  (N/A on ERB08)
    Bit 2: Port C Low polarity setting   (0 = inverted,  1 = normal)
    Bit 3: Port C High polarity setting  (0 = inverted,  1 = normal)
    Bit 4: Port A pull-up setting        (0 = pull down, 1 = pull up) (N/A on ERB08)
    Bit 5: Port B pull-up setting        (0 = pull down, 1 = pull up) (N/A on ERB08)
    Bit 6: Port C Low pull-up setting    (0 = pull down, 1 = pull up)
    Bit 7: Port C High pull-up setting   (0 = pull down, 1 = pull up)
  */
    
  PMD_SendOutputReport(fd, GET_STATUS, 0, 0, FS_DELAY);
  PMD_GetInputReport(fd, GET_STATUS, (__u8 *) &status, sizeof(status), FS_DELAY);
  return status;
}

float usbGetTemp_USBERB(int fd)
{
  __s16 temp;
  
  PMD_SendOutputReport(fd, GET_TEMP, 0, 0, FS_DELAY);
  PMD_GetInputReport(fd, GET_TEMP,  (__u8 *) &temp, sizeof(temp), FS_DELAY);
  return (temp/0.1);
}

void usbPrepareDownload_USBERB(int fd)
{
  /*
    This command puts the device into code update mode.  The unlock code must be correct as a
    further safety device.  Call this once before sending code with usbWriteCode.  If not in
    code update mode, any usbWriteCode will be ignored.  A usbReset command must be issued at
    the end of the code download in order to return the device to operation with the new code.
  */

  const __u8 unlock_code = 0xad;

  __u8 cmd = unlock_code;

  PMD_SendOutputReport(fd, PREPARE_DOWNLOAD, &cmd, sizeof(cmd), FS_DELAY);
}

void usbWriteCode_USBERB(int fd, __u32 address, __u8 count, __u8 data[])
{
  /*
    This command writes to the program memory in the device.  This command is not accepted
    unless the device is in update mode.  This command will normally be used when downloading
    a new hex file, so it supports memory ranges that may be found in the hex file.  

    The address ranges are:

    0x000000 - 0x007AFF:  Microcontroller FLASH program memory
    0x200000 - 0x200007:  ID memory (serial number is stored here on main micro)
    0x300000 - 0x30000F:  CONFIG memory (processor configuration data)
    0xF00000 - 0xF03FFF:  EEPROM memory

    FLASH program memory: The device must receive data in 64-byte segments that begin
    on a 64-byte boundary.  The data is sent in messages containing 32 bytes.  count
    must always equal 32.

    Other memory: Any number of bytes up to the maximum (32) may be sent.
    
  */

  struct t_arg {
    __u8 address[3];
    __u8 count;
    __u8 data[32];
  } arg;

  if (count > 32) count = 32;             // 32 byte max 
  memcpy(&arg.address[0], &address, 3);   // 24 bit address
  arg.count = count;                      // the number of byes of data (max 32)
  memcpy(&arg.data[0], data, count);      // the program data
  PMD_SendOutputReport(fd, WRITE_CODE, (__u8 *) &arg, count+4, FS_DELAY);
}

int usbReadCode_USBERB(int fd, __u32 address, __u8 count, __u8 data[])
{
  struct t_arg {
    __u8 address[3];
    __u8 count;
  } arg;

  int bRead;

  if ( count > 62 ) count = 62;  

  memcpy(&arg.address[0], &address, 3);   // 24 bit address
  arg.count = count;
  PMD_SendOutputReport(fd, READ_CODE, (__u8 *) &arg, sizeof(arg), FS_DELAY);
  bRead = PMD_GetInputReport(fd, READ_CODE,  data, count, FS_DELAY);
  return bRead;
}

void usbWriteSerial_USBERB(int fd, __u8 serial[8])
{
  // Note: The new serial number will be programmed but not used until hardware reset.
  
  PMD_SendOutputReport(fd, WRITE_SERIAL, serial, 8, FS_DELAY);
}
