// metro.config.js — extends Expo's default metro config to handle
// binary ML model assets (.onnx, .tflite) bundled with the app.
const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);

// Register ONNX and TFLite as binary asset extensions so Metro
// includes them in the bundle and expo-asset can resolve them.
config.resolver.assetExts.push('onnx', 'tflite');

module.exports = config;
