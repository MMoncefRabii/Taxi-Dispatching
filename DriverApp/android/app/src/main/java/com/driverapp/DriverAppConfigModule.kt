package com.driverapp

import com.facebook.react.ReactPackage
import com.facebook.react.bridge.NativeModule
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReactContextBaseJavaModule
import com.facebook.react.uimanager.ViewManager

class DriverAppConfigModule(context: ReactApplicationContext) :
    ReactContextBaseJavaModule(context) {
    override fun getName(): String = "DriverAppConfig"

    override fun getConstants(): MutableMap<String, Any> =
        mutableMapOf("apiBaseUrl" to BuildConfig.API_BASE_URL)
}

class DriverAppConfigPackage : ReactPackage {
    override fun createNativeModules(
        reactContext: ReactApplicationContext,
    ): List<NativeModule> = listOf(DriverAppConfigModule(reactContext))

    override fun createViewManagers(
        reactContext: ReactApplicationContext,
    ): List<ViewManager<*, *>> = emptyList()
}
