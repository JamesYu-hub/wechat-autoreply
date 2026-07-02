on run argv
    if (count of argv) is 1 and item 1 of argv is "--check-permission" then
        tell application "System Events" to return UI elements enabled
    end if

    if (count of argv) is 1 and item 1 of argv is "--request-access" then
        tell application "System Events"
            set isEnabled to UI elements enabled
            if not isEnabled then
                try
                    keystroke ""
                end try
            end if
            return isEnabled
        end tell
    end if

    if (count of argv) is 1 and item 1 of argv is "--test-access" then
        do shell script "open -b com.tencent.xinWeChat"
        delay 1
        tell application "System Events"
            tell process "WeChat" to set frontmost to true
            delay 0.5
            keystroke ""
            return "access test passed"
        end tell
    end if

    if (count of argv) is not 2 then error "Usage: osascript sendwechat.scpt CONTACT MESSAGE"

    set targetName to item 1 of argv
    set msgText to item 2 of argv

    do shell script "open -b com.tencent.xinWeChat"
    delay 1.5

    tell application "System Events"
        tell process "WeChat" to set frontmost to true
        keystroke "f" using {command down}
        delay 0.6

        set the clipboard to targetName
        keystroke "v" using {command down}
        delay 1.5
        key code 36
        delay 1.2

        set the clipboard to msgText
        keystroke "v" using {command down}
        delay 0.5
        key code 36
        delay 1
    end tell
end run
