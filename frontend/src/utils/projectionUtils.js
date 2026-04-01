/**
 * 坐标系转换工具
 * 用于处理不同坐标系之间的转换
 */

import proj4 from 'proj4';
import { register } from 'ol/proj/proj4';

// 常用中国坐标系定义
const projections = {
  // WGS84
  'EPSG:4326': '+proj=longlat +datum=WGS84 +no_defs',
  
  // Web墨卡托
  'EPSG:3857': '+proj=merc +a=6378137 +b=6378137 +lat_ts=0 +lon_0=0 +x_0=0 +y_0=0 +k=1 +units=m +nadgrids=@null +wktext +no_defs',
  
  // 北京54坐标系
  'EPSG:4214': '+proj=longlat +ellps=krass +towgs84=15.8,-154.4,-82.3,0,0,0,0 +no_defs',
  
  // 西安80坐标系
  'EPSG:4610': '+proj=longlat +a=6378140 +b=6356755.288157528 +units=degrees +no_defs',
  
  // CGCS2000
  'EPSG:4490': '+proj=longlat +ellps=GRS80 +no_defs',
  
  // 高斯-克吕格投影 (3度带)
  'EPSG:2361': '+proj=tmerc +lat_0=0 +lon_0=117 +k=1 +x_0=500000 +y_0=0 +ellps=krass +units=m +no_defs',
  
  // 高斯-克吕格投影 (6度带)
  'EPSG:2343': '+proj=tmerc +lat_0=0 +lon_0=114 +k=1 +x_0=500000 +y_0=0 +ellps=krass +units=m +no_defs',
};

/**
 * 初始化坐标系
 * 注册常用的坐标系定义
 */
export function initProjections() {
  // 注册所有预定义的坐标系
  Object.entries(projections).forEach(([code, def]) => {
    proj4.defs(code, def);
  });
  
  // 向OpenLayers注册proj4定义
  register(proj4);
  
  console.log('坐标系定义已初始化');
}

/**
 * 注册自定义坐标系
 * @param {string} code - 坐标系代码，如 'EPSG:xxxx'
 * @param {string} definition - proj4格式的坐标系定义
 */
export function registerProjection(code, definition) {
  if (!code || !definition) {
    console.error('注册坐标系失败：代码或定义为空');
    return;
  }
  
  try {
    // 注册到proj4
    proj4.defs(code, definition);
    
    // 更新OpenLayers
    register(proj4);
    
    console.log(`坐标系 ${code} 注册成功`);
    return true;
  } catch (error) {
    console.error(`注册坐标系 ${code} 失败:`, error);
    return false;
  }
}

/**
 * 解析坐标系字符串
 * 从后端返回的坐标系字符串中提取EPSG代码
 * @param {string} crsString - 坐标系字符串，如 'EPSG:4326' 或 'epsg:4326' 或 '+proj=longlat +datum=WGS84 +no_defs'
 * @returns {string} 标准化的EPSG代码，如 'EPSG:4326'，如果无法解析则返回 'EPSG:4326'
 */
export function parseProjection(crsString) {
  if (!crsString) return 'EPSG:4326';
  
  // 尝试从字符串中提取EPSG代码
  const epsgMatch = crsString.match(/EPSG:?(\d+)/i);
  if (epsgMatch) {
    return `EPSG:${epsgMatch[1]}`;
  }
  
  // 如果是完整的proj4定义，尝试注册并返回一个临时代码
  if (crsString.includes('+proj=')) {
    const tempCode = `EPSG:temp-${Date.now()}`;
    registerProjection(tempCode, crsString);
    return tempCode;
  }
  
  // 默认返回WGS84
  console.warn(`无法解析坐标系: ${crsString}，将使用WGS84`);
  return 'EPSG:4326';
}