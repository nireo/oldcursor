#pragma once
#include <ApplicationServices/ApplicationServices.h>

// Undocumented Apple C interfaces. No code is injected into another process.
typedef int CGSConnectionID;
extern CGSConnectionID CGSMainConnectionID(void);
extern CGError CGSRegisterCursorWithImages(CGSConnectionID, char *, bool, bool,
    CGSize, CGPoint, NSUInteger, CGFloat, CFArrayRef, int *);
extern CGError CGSSetRegisteredCursor(CGSConnectionID, char *, int *);
extern CGError CoreCursorUnregisterAll(CGSConnectionID);
extern CGError CoreCursorSet(CGSConnectionID, int);
extern CGError CGSSetSystemDefinedCursor(CGSConnectionID, int);
extern void CGSSetDockCursorOverride(CGSConnectionID, bool);
extern CGError CGSGetCursorScale(CGSConnectionID, float *);
extern CGError CGSSetCursorScale(CGSConnectionID, float);
